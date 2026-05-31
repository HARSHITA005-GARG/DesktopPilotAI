import os
import docker
from typing import Tuple

class DockerSandbox:
    """
    Provides an isolated, transient environment to execute LLM-generated Python code.
    Ensures the agent cannot accidentally break the host Windows OS or consume all RAM.
    """
    
    def __init__(self, workspace_dir: str = "./workspace"):
        # 1. Prepare the local volume map
        # This is the folder on your Windows host that the container will interact with
        self.workspace_dir = os.path.abspath(workspace_dir)
        os.makedirs(self.workspace_dir, exist_ok=True)
        
        # 2. Connect to the local Docker daemon (WSL2 backend)
        try:
            self.client = docker.from_env()
            self.image_name = "python:3.11-slim"
            
            # Pre-pull the image to prevent latency spikes during the first execution
            print(f"[Sandbox] Verifying {self.image_name} image...")
            try:
                self.client.images.get(self.image_name)
            except docker.errors.ImageNotFound:
                print(f"[Sandbox] Pulling {self.image_name}... this may take a moment.")
                self.client.images.pull(self.image_name)
                
        except Exception as e:
            print(f"[Sandbox Error] Fatal error connecting to Docker Desktop: {e}")

    def execute_code(self, code: str) -> Tuple[str, str]:
        """
        Writes the code to the mapped volume, executes it inside a locked-down 
        container, and captures stdout (success) or stderr (failure).
        """
        # 1. Write the raw code to the local workspace volume
        script_name = "agent_script.py"
        script_path = os.path.join(self.workspace_dir, script_name)
        
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(code)
            
        stdout_output = ""
        stderr_output = ""

        try:
            print("[Sandbox] Executing code in transient container...")
            
            # 2. Spin up, execute, and destroy in one fluid motion
            result = self.client.containers.run(
                image=self.image_name,
                command=f"python /app/{script_name}",
                # Bind-mount the Windows host directory to /app in the Linux container
                volumes={self.workspace_dir: {'bind': '/app', 'mode': 'rw'}},
                working_dir="/app",
                
                # Security & Resource Constraints
                remove=True,              # Destroy container instantly after running
                network_disabled=True,    # Prevent unauthorized web requests/downloads
                mem_limit="512m",         # Hard cap to protect your 24GB system RAM limit
                cpu_period=100000,
                cpu_quota=50000           # Throttle CPU to prevent system hangs
            )
            
            # If execution succeeds, decode the standard output
            stdout_output = result.decode("utf-8").strip()
            print(f"[Sandbox Success] Output captured.")
            
        except docker.errors.ContainerError as e:
            # 3. The Catch: This intercepts Python runtime errors (SyntaxError, etc.)
            # Your LangGraph orchestrator will feed this exact string back to the LLM
            stderr_output = e.stderr.decode("utf-8").strip()
            print(f"[Sandbox Failure] Captured stderr for LLM self-correction.")
            
        except Exception as e:
            # Catches Docker-level daemon issues or memory limits being hit
            stderr_output = f"System Execution Error: {str(e)}"
            print(f"[Sandbox System Error] {stderr_output}")
            
        finally:
            # 4. Clean up the script file so the workspace is pristine for the next run
            if os.path.exists(script_path):
                os.remove(script_path)
                
        return stdout_output, stderr_output