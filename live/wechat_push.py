"""Server酱微信推送辅助脚本 - 供 PowerShell 主脚本调用.

Usage: python wechat_push.py <title> <desp>
"""
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import SERVERCHAN_SENDKEY  # noqa: E402


def main() -> int:
    title = sys.argv[1] if len(sys.argv) > 1 else "AMV通知"
    desp = sys.argv[2] if len(sys.argv) > 2 else ""

    if not SERVERCHAN_SENDKEY:
        print(json.dumps({"code": -1, "msg": "SERVERCHAN_SENDKEY not configured"}, ensure_ascii=False))
        return 1

    url = "https://sctapi.ftqq.com/{}.send".format(SERVERCHAN_SENDKEY)
    data = urllib.parse.urlencode({"title": title, "desp": desp}).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        resp = urllib.request.urlopen(req, timeout=15)
        result = json.loads(resp.read().decode("utf-8"))
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("code") == 0 else 2
    except Exception as e:
        print(json.dumps({"code": -1, "msg": str(e)}, ensure_ascii=False))
        return 3


if __name__ == "__main__":
    sys.exit(main())
