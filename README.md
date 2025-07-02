# RAT Control Panel

Dieses Projekt ist ein Remote Administration Tool (RAT) für Forschungs- und Testzwecke.

## Features

- Multi-Client Verwaltung
- Discord-ähnliche Slash-Befehle mit Autovervollständigung
- Live-Screen-Streaming
- Dateiübertragung (Download/Upload)
- Keylogger (sofern möglich)
- Systeminformationen und Browserverlauf
- Sicheres Web-UI mit Authentifizierung

## Installation

1. Python 3.10+ installieren
2. Abhängigkeiten installieren:
   ```
   pip install -r requirements.txt
   ```
3. Server starten:
   ```
   python server.py
   ```
4. Client kompilieren:
   ```
   ./compile.bat
   ```

## Hinweise

- Nur für legale und ethische Zwecke verwenden!
- Standard-Login für das Web-UI: Nutzername `admin`, Passwort `supersecretpassword123`
- Diese Zugangsdaten können über die Umgebungsvariablen `ADMIN_USERNAME` und `ADMIN_PASSWORD` gesetzt werden.
- Die kompilierten Executables werden nach jedem Build automatisch im Ordner `executables/` im Repository gespeichert (siehe GitHub Actions Workflow).
- Dokumentation und weitere Hinweise folgen.

---

### Fehlerbehebung: Submodul-Fehler

Falls beim Klonen oder Arbeiten mit dem Repository folgende Fehlermeldung erscheint:

```
fatal: No url found for submodule path 'RAT' in .gitmodules
```

**Lösung:**  
Das Projekt verwendet keine Submodule. Die Datei `.gitmodules` kann gelöscht werden, oder der Befehl kann ignoriert werden.  
Falls das Problem weiterhin besteht, führe Folgendes aus:

```sh
git submodule deinit -f .
git rm --cached RAT
rm -f .gitmodules
```

Danach sollte das Repository wie gewohnt funktionieren.
