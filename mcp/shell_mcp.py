import subprocess
import time
import platform
import os
from langchain_core.tools import tool
from typing import Optional, Dict, Any, List


@tool("get_system_info")
async def get_system_info() -> Dict[str, Any]:
    """Get current system information for command execution context.
    
    Returns:
        dict: Essential system information for shell command generation
    """
    system = platform.system().lower()
    
    # Display-friendly names
    display_names = {
        "windows": "Windows",
        "linux": "Linux", 
        "darwin": "macOS"
    }
    
    return {
        "os_type": system,
        "display_name": display_names.get(system, system.title()),
        "platform": platform.platform(),
        "architecture": platform.architecture()[0],
        "python_version": platform.python_version(),
        "current_directory": os.getcwd(),
        "shell_type": os.environ.get("SHELL", "cmd.exe" if system == "windows" else "/bin/bash"),
        "path_separator": os.sep,
        "is_windows": system == "windows",
        "is_unix": system in ["linux", "darwin"],
        "home_directory": os.path.expanduser("~"),
        "user": os.environ.get("USER", os.environ.get("USERNAME", "unknown"))
    }


@tool("execute_shell")
async def execute_shell(command: str, timeout: int = 30, working_dir: Optional[str] = None) -> Dict[str, Any]:
    """Execute a shell command and return the result.
    
    Args:
        command (str): Shell command to execute
        timeout (int): Command timeout in seconds (default: 30)
        working_dir (str, optional): Working directory for command execution
        
    Returns:
        dict: Contains exit_code, stdout, stderr, execution_time, and system info
    """
    start_time = time.time()
    system_type = platform.system().lower()
    
    try:
        # Determine shell based on OS
        if system_type == "windows":
            # Use cmd.exe on Windows
            shell_cmd = ["cmd", "/c", command]
            use_shell = False
        else:
            # Use bash/sh on Unix-like systems
            shell_cmd = command
            use_shell = True
        
        # Use subprocess with timeout and capture output
        result = subprocess.run(
            shell_cmd,
            shell=use_shell,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=working_dir
        )
        
        execution_time = time.time() - start_time
        
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "execution_time": round(execution_time, 2),
            "command": command,
            "working_directory": working_dir or os.getcwd(),
            "system_type": system_type,
            "success": result.returncode == 0
        }
        
    except subprocess.TimeoutExpired:
        execution_time = time.time() - start_time
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": f"Command timed out after {timeout} seconds",
            "execution_time": round(execution_time, 2),
            "command": command,
            "working_directory": working_dir or os.getcwd(),
            "system_type": system_type,
            "success": False
        }
    except Exception as e:
        execution_time = time.time() - start_time
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": str(e),
            "execution_time": round(execution_time, 2),
            "command": command,
            "working_directory": working_dir or os.getcwd(),
            "system_type": system_type,
            "success": False
        }