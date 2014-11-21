:: recipe: http://ss64.com/nt/syntax-getdate.html
:: found via http://stackoverflow.com/questions/1192476/format-date-and-time-in-a-windows-batch-script

@ECHO OFF

:: parameters
set framerate=25

set keysecs=60
:: in seconds

set usewindowtitle=0
set windowtitle=

set usevideosize=0
set width=0
set height=0
set left=0
set top=0

:paramloop
if not "%1"=="" (
	if "%1"=="-framerate" (
		set framerate=%2
		shift
	)
	if "%1"=="-title" (
		set windowtitle=%2
		shift
		set usewindowtitle=1
	)
	if "%1"=="-wh" (
		set width=%2
		set height=%3
		shift
		shift
		set usevideosize=1
	)
	if "%1"=="-xy" (
		set left=%2
		set top=%3
		shift
		shift
	)
	shift
	goto paramloop
)

:: build timestamp

:: default
set timestamp=_

:: Check WMIC is available
WMIC.EXE Alias /? >NUL 2>&1 || GOTO warn_wmi

:: Use WMIC to retrieve date and time
FOR /F "skip=1 tokens=1-6" %%G IN ('WMIC Path Win32_LocalTime Get Day^,Hour^,Minute^,Month^,Second^,Year /Format:table') DO (
   IF "%%~L"=="" goto timeparts_done
      Set _yyyy=%%L
      Set _mm=00%%J
      Set _dd=00%%G
      Set _hour=00%%H
      SET _minute=00%%I
      SET _second=00%%K
)
echo what happens here?
exit /b -1

:timeparts_done
:: Pad digits with leading zeros
Set _mm=%_mm:~-2%
Set _dd=%_dd:~-2%
Set _hour=%_hour:~-2%
Set _minute=%_minute:~-2%
Set _second=%_second:~-2%
set /a "_yy=_yyyy-2000"

set timestamp=%_yy%%_mm%%_dd%-%_hour%%_minute%%_second%
goto timestamp_done

:warn_wmi
echo WMIC is not available to read current time

:timestamp_done


:main
:: file name
FOR /F "usebackq" %%i IN (`hostname`) DO SET HOSTNAME=%%i
set FILENAME=screencap-%timestamp%-%HOSTNAME%.mov

set sizeopt=
set sizereport=auto
if %usevideosize%==1 (
	set sizeopt=-video_size %width%x%height%
	set sizereport=%width% x %height%
)

set input=desktop
if %usewindowtitle%==1 (
	set input=title=%windowtitle%
)

set /a "keyint=keysecs*framerate"

echo frame rate: %framerate% fps
echo size: %sizereport%
echo position: %left% x %top%
echo input: %input%
echo writing to %FILENAME%
echo CWD:
echo   %cd%

if exist %FILENAME% (
	echo ERROR: file already exists!
	exit /b -1
)

echo.

::  -video_size 1920x1200
::ffmpeg  -f gdigrab -r 10 -i desktop -pix_fmt yuv444p -c:v libx264 -preset:v baseline -preset:v ultrafast -tune:v stillimage -tune:v zerolatency -crf 0 %FILENAME%

ffmpeg -f gdigrab -framerate %framerate% %sizeopt% -offset_x %left% -offset_y %top% -i %input% -c:v qtrle -g %keyint% %FILENAME%

