@echo off
echo Agar purani exe chal rahi ho to band ki ja rahi hai...
taskkill /f /im SuperstorePOS.exe >nul 2>&1
timeout /t 2 /nobreak >nul
echo.
echo Exe ban rahi hai, 1-2 minute intezar karein...
python -m PyInstaller --noconfirm --clean --onefile --windowed --name SuperstorePOS main.py
if errorlevel 1 goto failed
echo.
echo Mukammal! Nayi exe yahan hai:  dist\SuperstorePOS.exe
pause
exit /b 0

:failed
echo.
echo ERROR: exe nahi ban saki. Upar likha hua laal error dekhein.
echo (Aksar wajah: exe chal rahi hai ya antivirus ne roka hai. Band karke dobara chalayen.)
pause
exit /b 1