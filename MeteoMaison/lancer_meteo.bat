
@echo off
cd /d C:\Users\olivi\MeteoMaison

"C:\Users\olivi\MeteoMaison\.venv\Scripts\python.exe" "C:\Users\olivi\MeteoMaison\recuperer_tuya.py" >> "C:\Users\olivi\MeteoMaison\acquisition.log" 2>&1
