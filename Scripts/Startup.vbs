Set ws = CreateObject("Wscript.Shell")
' ws.run "timeout /t 10 /nobreak", vbhide, true
ws.run "wsl --distribution debian --user shawn --shell-type login /home/shawn/init.wsl", vbhide
