import asyncio
import time
from pathlib import Path
from typing import Any, Dict, Tuple

from .task import Task


async def main(dirs_path: Tuple[Path], config: Dict[str, Any], **flags: bool):
    print(type(dirs_path), dirs_path)
    print(type(flags), flags)
    print(config)
    async with asyncio.TaskGroup() as tg:
        for dir_path in dirs_path:
            task = Task(config, **flags)
            tg.create_task(task.gen_recording(dir_path))
        print(f"started at {time.strftime('%X')}")
    print(f"finished at {time.strftime('%X')}")
