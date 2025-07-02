# RAT Control Panel

Dieses Projekt ist ein Remote Administration Tool (RAT) für Forschungs- und Testzwecke.

## Features

- Multi-Client Verwaltung (gleichzeitige Steuerung mehrerer Clients)
- Discord-ähnliche Slash-Befehle mit Autovervollständigung
- Live-Screen-Streaming (VNC-ähnlich)
- Dateiübertragung (Download/Upload)
- Keylogger (sofern möglich)
- Systeminformationen und Browserverlauf
- Verzeichnisnavigation (`ls`, `cd`)
- Verschlüsselung/Entschlüsselung von Dateien/Verzeichnissen (`encrypt`, `decrypt`)
- Sicheres Web-UI mit Authentifizierung (Basic Auth)
- Kompatibel mit Windows, Linux und macOS (Client & Server)
- Persistenz auf Windows (Autostart)
- Benachrichtigung bei neuer Verbindung (ntfy.sh)
- Debug-Panel für Fehleranalyse im Web-UI

## Unterstützte Slash-Befehle

| Befehl                | Beschreibung                                         |
|-----------------------|------------------------------------------------------|
| `/help`               | Zeigt die Hilfe an                                   |
| `/exec`               | Führe einen Shell-Befehl aus                         |
| `/screenshot`         | Screenshot des Bildschirms                           |
| `/download`           | Datei herunterladen (Pfad angeben)                   |
| `/upload`             | Datei zum Client hochladen                           |
| `/history`            | Browserverlauf anzeigen                              |
| `/keylogger`          | Keylogger-Log anzeigen                               |
| `/ls`                 | Verzeichnis auflisten                                |
| `/cd`                 | Verzeichnis wechseln                                 |
| `/encrypt`            | Verzeichnis rekursiv verschlüsseln                   |
| `/decrypt`            | Verzeichnis rekursiv entschlüsseln (Pfad und Schlüssel)|
| `/systeminfo`         | Systeminformationen anzeigen                         |
| `/shutdown`           | Client herunterfahren                                |
| `/restart`            | Client neustarten                                    |
| `/screenstream_start` | Live-Screen starten                                  |
| `/screenstream_stop`  | Live-Screen stoppen                                  |

**Beispiel für Verschlüsselung/Entschlüsselung:**
- `/encrypt C:\Users\test\Documents`
- `/decrypt C:\Users\test\Documents 0123456789abcdef...`

## Installation

1. **Python 3.10+ installieren**
2. **Abhängigkeiten installieren:**
   ```
   pip install -r requirements.txt
   ```
3. **Server starten:**
   ```
   python server.py
   ```
4. **Client kompilieren:**
   ```
   ./compile.bat
   ```
   oder manuell mit PyInstaller:
   ```
   pyinstaller --noconsole --onefile client.py
   ```

## Systemvoraussetzungen

- **Server:** Python 3.10+, FastAPI, Uvicorn, websockets, cryptography, etc.
- **Client:** Python 3.10+, mss, pillow, pynput, pyautogui, cryptography, websockets, etc.
- **Web-UI:** Moderne Browser (Chrome, Firefox, Edge, Safari)

## Hinweise

- **Nur für legale und ethische Zwecke verwenden!**
- Standard-Login für das Web-UI: Nutzername `admin`, Passwort `supersecretpassword123`
- Diese Zugangsdaten können über die Umgebungsvariablen `ADMIN_USERNAME` und `ADMIN_PASSWORD` gesetzt werden.
- Die kompilierten Executables werden nach jedem Build automatisch im Ordner `executables/` im Repository gespeichert (siehe GitHub Actions Workflow).
- Persistenz (Autostart) ist nur auf Windows implementiert.
- Die Keylogger-Funktion benötigt das Modul `pynput` und funktioniert ggf. nicht in allen Umgebungen.
- Für Browserverlauf werden Chrome, Edge und Firefox unterstützt (je nach OS).
- Die Kommunikation erfolgt verschlüsselt über WebSockets (wss).

## Troubleshooting

- **Fehler beim Starten:** Prüfe, ob alle Abhängigkeiten installiert sind (`pip install -r requirements.txt`).
- **Submodul-Fehler:**  
  Das Projekt verwendet keine Submodule. Die Datei `.gitmodules` kann gelöscht werden, oder der Befehl kann ignoriert werden.  
  Falls das Problem weiterhin besteht, führe Folgendes aus:
  ```sh
  git submodule deinit -f .
  git rm --cached RAT
  rm -f .gitmodules
  ```
- **Web-UI nicht erreichbar:** Stelle sicher, dass der Server läuft und der Port (Standard: 8000) offen ist.
- **Client verbindet nicht:** Prüfe die SERVER_URI in `client.py` und die Netzwerkverbindung.

## Sicherheit

- **Niemals für illegale Zwecke verwenden!**
- Der Code ist zu Forschungs- und Testzwecken gedacht.
- Setze sichere Passwörter für das Web-UI.
- Der Entwickler übernimmt keine Haftung für Schäden oder Missbrauch.

## Entwicklung

- **Frontend:** HTML, Vanilla JS (siehe `index.html`)
- **Backend:** FastAPI (siehe `server.py`)
- **Client:** Python (siehe `client.py`)
- **Build:** Siehe GitHub Actions Workflow `.github/workflows/build-clients.yml`

## Lizenz

MIT License – siehe [LICENSE](LICENSE)

---

### Kontakt

Für Fragen oder Beiträge:  
- GitHub Issues  
- Maintainer: NM und JK

---
