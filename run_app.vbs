Set objShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

currentFolder = fso.GetParentFolderName(WScript.ScriptFullName)

command = "cmd /c cd /d """ & currentFolder & """ && .venv\Scripts\python.exe -m streamlit run app.py --server.headless true"

objShell.Run command, 0, False

WScript.Sleep 4000
objShell.Run "http://localhost:8501"