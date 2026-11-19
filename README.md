# Ente CLI Container (Rust)

Inoffizielles Multi-Arch-Container-Image für die neue, in Rust geschriebene
[Ente CLI](https://ente.com/help/cli/). Die alte Go-CLI wird nicht verwendet.

## Automatische Builds und Changelogs

Der [GitHub-Actions-Workflow](.github/workflows/container.yml):

1. prüft täglich um **05:23 UTC** die Releases von `ente/ente`;
2. wählt die semantisch höchste stabile Version mit Tag `ente-cli-vX.Y.Z`
   (keine Go-Releases, Entwürfe oder Vorabversionen);
3. überspringt bereits veröffentlichte Container-Versionen;
4. baut die unveränderten Quellen des Release-Tags mit `Cargo.lock` nativ für
   **linux/amd64** und **linux/arm64**, mit generischen Rust- und C/C++-CPU-Flags;
5. testet beide Images als Nicht-Root-Benutzer und prüft auf amd64 zusätzlich
   HTTPS/TLS unter QEMU mit einer **Nehalem-CPU ohne AVX**;
6. veröffentlicht genau diese getesteten Images als Multi-Arch-Image auf **GHCR**;
7. erstellt ein GitHub Release `vX.Y.Z` mit den **unveränderten Upstream-Release-Notes**,
   Quellcode-Links und dem Image-Digest.

Image: `ghcr.io/kevincfechtel/ente-cli`

Tags: `:X.Y.Z` und `:latest`, außerdem `:X.Y.Z-amd64` und `:X.Y.Z-arm64`.
Die GitHub Releases sind der Container-Changelog;
es werden dafür keine automatischen Commits auf `main` benötigt.
Beim ersten Lauf wird nur die aktuellste stabile Version gebaut, kein historisches
Archiv. Auch nach einer Pause wird die aktuellste Version übernommen; dazwischen
erschienene Releases werden nicht nachträglich gebaut.

Pushes auf `main` bauen die aktuelle CLI-Version erneut, damit Änderungen am
Container direkt veröffentlicht werden. Pull Requests testen beide Architekturen,
veröffentlichen aber nichts. Ein manueller Lauf unter **Actions → Ente CLI container
→ Run workflow** prüft ebenfalls auf Updates; mit `force` wird die aktuelle
Version erneut gebaut, etwa für Basisimage-Sicherheitsupdates.
Bei einem Rebuild werden die Image-Tags und Release Notes aktualisiert; wer ein
unveränderliches Image benötigt, verwendet den Digest aus dem Release.
Der Git-Tag eines bestehenden Releases bleibt beim ursprünglichen Commit;
der tatsächlich verwendete Container-Quellstand steht in den Release Notes und
im OCI-Label `org.opencontainers.image.revision`.

Fehlgeschlagene Builds oder Pushes erzeugen kein neues erfolgreiches GitHub Release;
bei noch nicht veröffentlichten Versionen versucht der nächste tägliche Lauf es erneut.
Schlägt ein Rebuild einer bereits veröffentlichten Version fehl, erneut mit `force`
starten oder nach einem weiteren Push auf `main` wiederholen.
Fehlende Upstream-Assets und API-Fehler brechen den Lauf ab, statt versehentlich
eine andere CLI-Version zu veröffentlichen.

### Synology und Prozessoren ohne AVX

Das offizielle amd64-Binary von Ente CLI 0.4.5 führt in der Kryptografie-Bibliothek
`ring` eine AVX-Anweisung aus. Auf beispielsweise einem Intel Celeron J4125
führt das beim Login oder bei HTTPS-Zugriffen zu `SIGILL` / Exit-Code **132**.
Dieses Image baut deshalb die CLI samt nativen Abhängigkeiten selbst, ohne
AVX als Voraussetzung. Der Quellcode der CLI bleibt unverändert.
Der zusätzliche Test übt die TLS-Zertifikatsprüfung gegen einen lokalen
Testserver aus – nicht nur `--version`. Er benötigt weder ein Ente-Konto noch
Zugangsdaten und kontaktiert keinen echten Ente-Server.

Nach Push der Container-Änderung auf `main` wird auch eine bereits veröffentlichte
CLI-Version neu gebaut. Erst wenn alle Prüfungen bestanden wurden, werden deren
Image-Tag und `latest` aktualisiert. Anschließend auf dem Docker-Host im
Compose-Verzeichnis ausführen:

```sh
sudo docker compose pull
sudo docker compose up -d
```

Compose-Konfiguration, Vault-Key sowie Config- und Export-Volumes beibehalten;
kein `down -v` verwenden. Eine Digest-Fixierung muss ausdrücklich auf den neuen
Digest geändert werden. Ein reiner Container-Neustart lädt kein neues Image.

## Einmalige Einrichtung

1. Änderungen committen und nach `main` pushen. GitHub Actions muss im Repo
   aktiviert sein; der Push startet den ersten Build.
2. Der Workflow verwendet das vorhandene `GITHUB_TOKEN` mit `contents: write`
   und `packages: write`. Ein eigener PAT oder Registry-Secret ist nicht nötig.
   Repository-/Organisationsrichtlinien müssen diese Rechte erlauben.
3. Nach dem ersten Push das GHCR-Paket bei Bedarf unter **Package settings →
   Change visibility → Public** öffentlich machen. Neue Pakete können zunächst
   privat sein; dann benötigen Pulls eine Anmeldung.
4. Läuft der Workflow in einem Fork, wird automatisch
   `ghcr.io/<owner>/<repo>` in Kleinschreibung verwendet.

GitHub kann geplante Läufe verzögern und deaktiviert sie bei öffentlichen Repos
nach 60 Tagen ohne Aktivität. In diesem Fall den Zeitplan unter Actions wieder
aktivieren. Der Zeitplan läuft nur auf dem Standardbranch.

## Verwendung

```sh
docker run --rm ghcr.io/kevincfechtel/ente-cli:latest --version
docker run --rm ghcr.io/kevincfechtel/ente-cli:latest --help
```

Die CLI ist der Entrypoint; Argumente folgen direkt nach dem Image-Namen.
Sie läuft als **UID/GID 1000:1000**. Das CLI-Home liegt unter `/config`;
Exportziele können unter `/export` eingebunden werden.

### Einloggen und Fotos exportieren

Ein Container hat keinen System-Schlüsselbund. Deshalb benötigt die Rust-CLI
einen eigenen Vault-Key, der bei jedem Aufruf gleich bleiben muss.

```sh
umask 077
mkdir -p "$HOME/.config/ente-cli-container"
# Nur einmal ausführen; eine vorhandene Datei niemals überschreiben.
(set -C; docker run --rm ghcr.io/kevincfechtel/ente-cli:latest \
  vault key generate > "$HOME/.config/ente-cli-container/vault-key")
export ENTE_CLI_VAULT_KEY="$(cat "$HOME/.config/ente-cli-container/vault-key")"

docker volume create ente-cli-config
docker volume create ente-cli-export

docker run --rm -it \
  --env ENTE_CLI_VAULT_KEY \
  --mount source=ente-cli-config,target=/config \
  ghcr.io/kevincfechtel/ente-cli:latest account login --app photos

docker run --rm \
  --env ENTE_CLI_VAULT_KEY \
  --mount source=ente-cli-config,target=/config \
  --mount source=ente-cli-export,target=/export \
  ghcr.io/kevincfechtel/ente-cli:latest photos export /export --no-input
```

Vault-Key getrennt vom CLI-Home sicher aufbewahren und sichern. Ohne diesen
Schlüssel lässt sich der Vault nicht öffnen. Umgebungsvariablen können von
Benutzern mit Docker-Zugriff eingesehen werden.
Bei Bind-Mounts müssen die Ordner für UID/GID 1000:1000 schreibbar sein
(alternativ `--user UID:GID` verwenden und Zugriffsrechte entsprechend setzen).
Ein Zeitplan für regelmäßige Fotoexporte ist nicht Teil dieses Images.

Weitere Befehle: [Accounts](https://ente.com/help/cli/accounts),
[Automation](https://ente.com/help/cli/automation),
[Migration von der Go-CLI](https://ente.com/help/cli/migration).

## Lokal bauen und testen

Die Version wird bewusst explizit übergeben; `latest` wird nicht im Dockerfile
aufgelöst.

```sh
python3 -m unittest discover -s tests -v
python3 scripts/prepare_release.py --repository KevinCFechtel/ente-cli --force
# Erkannte Version steht in .release/release.json.
docker build --build-arg ENTE_CLI_VERSION=0.4.5 -t ente-cli:local .
bash scripts/smoke-test.sh ente-cli:local 0.4.5
# Zusätzlich auf einem Linux-amd64-Host mit Docker, OpenSSL und qemu-user-static:
python3 scripts/test_no_avx.py ente-cli:local 0.4.5
```

Die Skripte benötigen Python **3.9+** ohne zusätzliche Python-Pakete.
Für API-Abfragen kann optional `GH_TOKEN` gesetzt werden, um das höhere
authentifizierte GitHub-Rate-Limit zu nutzen.
Quellcode-Builds dauern insbesondere beim ersten Lauf länger als Binary-Downloads.
Dependabot prüft wöchentlich die Actions-Versionen und die Docker-Basisimages.

## Lizenzen und Quellcode

Die Builddateien dieses Repos stehen unter [BSD-3-Clause](LICENSE).
Die aus unveränderten Quellen selbst gebaute Ente-CLI steht unter der **AGPL-3.0**;
ihre Lizenz wird dadurch nicht geändert. Lizenztexte und versionsgenaue
Quellcode-Links liegen im Image unter `/usr/share/licenses/ente-cli/`.
Jedes Container-Release verlinkt außerdem den passenden
[Upstream-Quellcode samt Build-Workflow](https://github.com/ente/ente).
