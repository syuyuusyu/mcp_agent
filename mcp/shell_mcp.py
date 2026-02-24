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
async def execute_shell(command: str, timeout: int = 30, working_dir: Optional[str] = None) -> str:
    """Execute a shell command and return the result as a formatted string.
    
    Args:
        command (str): Shell command to execute
        timeout (int): Command timeout in seconds (default: 30)
        working_dir (str, optional): Working directory for command execution
        
    Returns:
        str: Formatted execution result including stdout, stderr, and exit code
    """
    start_time = time.time()
    system_type = platform.system().lower()
    cwd = working_dir or os.getcwd()
    
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
        
        output_lines = [f"$ {command}"]
        if result.stdout and result.stdout.strip():
            output_lines.append(result.stdout.strip())
        if result.stderr and result.stderr.strip():
            output_lines.append(f"[stderr]\n{result.stderr.strip()}")
        
        if result.returncode != 0:
            output_lines.append(f"[Exit Code: {result.returncode}]")
        
        return "\n".join(output_lines)

    except subprocess.TimeoutExpired:
        execution_time = time.time() - start_time
        return f"$ {command}\n[Error: Command timed out after {timeout} seconds]"
        
    except Exception as e:
        execution_time = time.time() - start_time
        return f"$ {command}\n[Error: {str(e)}]"