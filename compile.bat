pyinstaller --noconsole --onefile --paths=C:\Users\%user%\.pyenv\pyenv-win\versions\3.13.1\Lib\site-packages -i icon.ico .\client.py

move dist\client.exe .
rmdir /s /q dist
del /F /Q client.spec
rmdir /s /q build