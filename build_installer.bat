@echo off
rem Pehle exe banata hai, phir Inno Setup se SuperstorePOS_Setup.exe (installer) banata hai.
call build.bat nopause
if errorlevel 1 goto failed

set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
if "%ISCC%"=="" goto noinno

"%ISCC%" installer.iss
if errorlevel 1 goto failed
echo.
echo Mukammal! Installer yahan hai:  installer_output\SuperstorePOS_Setup.exe
pause
exit /b 0

:noinno
echo.
echo Inno Setup nahi mila. Isay https://jrsoftware.org/isdl.php se install karein, phir ye file dobara chalayen.
pause
exit /b 1

:failed
echo.
echo ERROR: installer nahi ban saka. Upar likha hua error dekhein.
pause
exit /b 1