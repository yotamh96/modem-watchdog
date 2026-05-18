import asyncio
import sys


async def probe():
    for i in range(3):
        proc = await asyncio.create_subprocess_exec(
            "qmicli",
            "--device-open-proxy",
            "--device=/dev/cdc-wdm0",
            "--dms-get-revision",
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=2.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            print("attempt " + str(i + 1) + ": TIMEOUT", file=sys.stderr)
            await asyncio.sleep(0.5)
            continue
        print("attempt " + str(i + 1) + ": exit=" + str(proc.returncode), file=sys.stderr)
        if proc.returncode != 0:
            print("  stderr: " + stderr.decode(errors="replace")[:200], file=sys.stderr)
        else:
            print("  stdout: " + stdout.decode(errors="replace")[:200], file=sys.stderr)
        if i < 2:
            await asyncio.sleep(0.5)


asyncio.run(probe())
