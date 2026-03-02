from __future__ import annotations

import os
import time
from email import policy
from email.parser import BytesParser
from pathlib import Path

from aiosmtpd.controller import Controller


WORK_DIR = Path(os.getenv("WORK_DIR", "/data/work"))
SMTP_PORT = int(os.getenv("SMTP_PORT", "2525"))


class AttachmentHandler:
    async def handle_DATA(self, server, session, envelope):
        msg = BytesParser(policy=policy.default).parsebytes(envelope.content)

        saved = 0
        WORK_DIR.mkdir(parents=True, exist_ok=True)

        for part in msg.iter_attachments():
            filename = part.get_filename() or ""
            if not filename.endswith("SHARPY.txt"):
                continue
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            target = WORK_DIR / filename
            target.write_bytes(payload)
            saved += 1

        print(f"SMTP message processed: saved {saved} SHARPY attachment(s)")
        return "250 OK"


def main() -> None:
    handler = AttachmentHandler()
    controller = Controller(handler, hostname="0.0.0.0", port=SMTP_PORT)
    controller.start()
    print(f"SMTP ingest listening on port {SMTP_PORT}")

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        controller.stop()


if __name__ == "__main__":
    main()
