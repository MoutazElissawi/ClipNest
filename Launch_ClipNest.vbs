Option Explicit
Dim shell, files, folder, pythonw, command
Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
folder = files.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = folder
pythonw = files.BuildPath(folder, "runtime\pythonw.exe")
If Not files.FileExists(pythonw) Then pythonw = files.BuildPath(folder, ".venv\Scripts\pythonw.exe")
If files.FileExists(pythonw) Then
    command = Chr(34) & pythonw & Chr(34) & " -s -E " & Chr(34) & files.BuildPath(folder, "Launch_ClipNest.pyw") & Chr(34)
Else
    MsgBox "ClipNest needs its first-time setup. The setup window will close when ClipNest opens.", vbInformation, "ClipNest setup"
    command = Chr(34) & files.BuildPath(folder, "Start_ClipNest.bat") & Chr(34)
End If
On Error Resume Next
shell.Run command, 1, False
If Err.Number <> 0 Then
    MsgBox "ClipNest could not start: " & Err.Description & vbCrLf & "Run Start_ClipNest.bat to check setup.", vbExclamation, "ClipNest"
End If
