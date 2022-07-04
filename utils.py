import psutil, os, time

my_process_name = "main.py"

def kill_other_instances():
    my_pid = os.getpid()

    # iterate through all running processes
    for p in psutil.process_iter():
        cmd = p.cmdline()
        if len(cmd) > 1:
            if cmd[0] == "python":
                if my_process_name in cmd[1]:
                    if not p.pid == my_pid:
                        print("Stopping existing process",cmd)
                        p.kill()
                        time.sleep(1)   # Seems like a good idea

if __name__ == "__main__":
    print("Hello, I am ",__file__)
    kill_other_instances()
    while True:
        time.sleep(1)
