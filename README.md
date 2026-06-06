# DeckShare

DeckShare is a small Windows desktop utility for copying selected folders to a Steam Deck over SSH/SFTP.

## Requirements

- Python 3.10+.
- Python package dependencies from `requirements.txt`.
- SSH enabled on Steam Deck.

On Steam Deck, enable and start SSH:

```bash
sudo systemctl enable --now sshd
passwd
```

The default connection profile is:

- Host: `steamdeck.local`
- User: `deck`
- Port: `22`
- Remote folder: `/home/deck/DeckShare`

## Run

Double-click `run.bat`, or run:

```powershell
python -m pip install --target .deps -r requirements.txt
python deckshare.py
```

You can also double-click `install_requirements.bat` once, then use `run.bat`.

Add Windows directories, choose a Deck destination for each selected folder, check SSH, then press **Transfer**. The default Deck path is used for newly added folders, but every folder can be pointed to its own Deck directory. DeckShare copies the contents of each selected Windows folder into its Deck destination; it does not create an extra remote folder with the Windows folder name. Settings are saved in `%APPDATA%\DeckShare\config.json`. If that location is not writable, DeckShare falls back to `.deckshare\config.json` next to the app.

## Notes

- The UI supports Russian and English. Use the language selector in the top-right corner.
- Login can use either the Steam Deck user password or a private SSH key.
- Passwords are not saved in the config file. If enabled, DeckShare stores the SSH password in the operating system credential store via `keyring`; the config only keeps a non-secret lookup key.
- Transfer engines:
  - `Compatible SFTP` uses Paramiko, supports password login and saved passwords, but can be slower.
  - `Fast OpenSSH` uses Windows `ssh.exe`, is intended for SSH key/agent login, and keeps the same temporary-file verification flow.
- `Parallel files` controls how many files can upload at the same time. Start with `1` or `2`; higher values can help many small files but may hurt Steam Deck microSD writes.
- Existing final files are skipped when size matches. New or changed files are uploaded to a temporary `.deckshare-part` file, verified with SHA-256, then used to replace the final file.
- If transfer is stopped during a file upload, DeckShare tries to remove the current `.deckshare-part` file automatically.
- During upload, the progress table shows every active file, destination folder, speed, percentage, and per-file ETA. Total ETA is shown above the table and is based on aggregate transfer speed.
- Extra files already present on the Steam Deck are not deleted.
- If `steamdeck.local` does not resolve on Windows, use the Steam Deck IP address shown in network settings. Bonjour/mDNS support can also make `.local` names work on Windows.
