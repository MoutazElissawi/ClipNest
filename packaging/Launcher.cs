// Runs the bundled CPython DLL in this process. No pythonw child/wrapper process.
// Compatible with the Windows .NET Framework C# compiler and CPython 3.11–3.13.
using System;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;

internal static class Launcher
{
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr LoadLibraryExW(string name, IntPtr file, uint flags);
    [DllImport("kernel32.dll", CharSet = CharSet.Ansi, ExactSpelling = true, SetLastError = true)]
    private static extern IntPtr GetProcAddress(IntPtr module, string name);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int MessageBoxW(IntPtr owner, string text, string title, uint flags);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate void SetPythonHome(IntPtr home);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate int PythonMain(int argc, IntPtr argv);

    private static Delegate Function(IntPtr module, string name, Type type)
    {
        IntPtr address = GetProcAddress(module, name);
        if (address == IntPtr.Zero) throw new InvalidOperationException("Missing Python function: " + name);
        return Marshal.GetDelegateForFunctionPointer(address, type);
    }

    [STAThread]
    private static int Main(string[] args)
    {
        IntPtr home = IntPtr.Zero, argv = IntPtr.Zero;
        IntPtr[] strings = null;
        try
        {
            string exe = Assembly.GetExecutingAssembly().Location;
            string folder = Path.GetDirectoryName(exe);
#if RECORDER
            // host_command provides the private runtime explicitly after relocating
            // this host beside the OBS helper EXEs. Preserve inherited pipe handles.
            string runtime = Environment.GetEnvironmentVariable("PYTHONHOME");
            if (String.IsNullOrEmpty(runtime) || !Path.IsPathRooted(runtime))
                throw new InvalidOperationException("Recorder runtime was not specified by ClipNest.");
            string[] arguments = new string[args.Length + 1];
            arguments[0] = exe;
            Array.Copy(args, 0, arguments, 1, args.Length);
#else
            string runtime = Path.Combine(folder, "runtime");
            // Never inherit a global/user Python installation into the application.
            Environment.SetEnvironmentVariable("PYTHONHOME", null);
            Environment.SetEnvironmentVariable("PYTHONPATH", null);
            Environment.SetEnvironmentVariable("PYTHONNOUSERSITE", "1");
            string[] arguments;
            if (args.Length == 2 && args[0] == "--check-runtime")
            {
                // Build-time check runs in this exact branded executable and
                // writes a report because the GUI executable has no console.
                string report = Path.GetFullPath(args[1]);
                Environment.SetEnvironmentVariable("CLIPNEST_LAUNCHER_REPORT", report);
                arguments = new string[] { exe, "-s", "-E", "-c",
                    "import sys,os,json,ssl,ctypes,PySide6,psutil,numpy; " +
                    "from pathlib import Path; from PySide6 import QtWidgets,QtMultimedia; " +
                    "assert all(Path(m.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()) for m in (PySide6,psutil,numpy)); " +
                    "Path(os.environ['CLIPNEST_LAUNCHER_REPORT']).write_text(json.dumps(dict(executable=sys.executable,prefix=sys.prefix)),encoding='utf-8')" };
            }
            else
            {
                arguments = new string[args.Length + 4];
                arguments[0] = exe; arguments[1] = "-s"; arguments[2] = "-E";
                arguments[3] = Path.Combine(folder, "Launch_ClipNest.pyw");
                Array.Copy(args, 0, arguments, 4, args.Length);
            }
#endif
            runtime = Path.GetFullPath(runtime);
            // Generated at build time, so no ambiguous DLL probing/version fallback.
            string dll = Path.Combine(runtime, BuildInfo.PythonDll);
            IntPtr module = LoadLibraryExW(dll, IntPtr.Zero, 0x00001100);
            if (module == IntPtr.Zero)
                throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error(), "Cannot load " + dll);
            home = Marshal.StringToHGlobalUni(runtime);
            SetPythonHome setHome = (SetPythonHome)Function(module, "Py_SetPythonHome", typeof(SetPythonHome));
            PythonMain main = (PythonMain)Function(module, "Py_Main", typeof(PythonMain));
            setHome(home);
            strings = new IntPtr[arguments.Length];
            argv = Marshal.AllocHGlobal(IntPtr.Size * (arguments.Length + 1));
            for (int i = 0; i < arguments.Length; i++)
            {
                strings[i] = Marshal.StringToHGlobalUni(arguments[i]);
                Marshal.WriteIntPtr(argv, i * IntPtr.Size, strings[i]);
            }
            Marshal.WriteIntPtr(argv, arguments.Length * IntPtr.Size, IntPtr.Zero);
            return main(arguments.Length, argv);
        }
        catch (Exception error)
        {
#if RECORDER
            Console.Error.WriteLine("ClipNest Recorder could not start: " + error);
#else
            MessageBoxW(IntPtr.Zero, "ClipNest could not start. Reinstall ClipNest to restore its private runtime.\n\n" + error.Message,
                "ClipNest startup error", 0x10);
#endif
            return 1;
        }
        finally
        {
            if (strings != null) foreach (IntPtr item in strings) if (item != IntPtr.Zero) Marshal.FreeHGlobal(item);
            if (argv != IntPtr.Zero) Marshal.FreeHGlobal(argv);
            if (home != IntPtr.Zero) Marshal.FreeHGlobal(home);
        }
    }
}
