# -*- coding: utf-8 -*-
import configparser
import json
import os
import sys
import warnings

# 屏蔽 requests 对 chardet/urllib3 的版本误报（环境里 reportlab 装的 chardet 版本超范围，不影响功能）
warnings.filterwarnings("ignore", message=".*doesn't match a supported version.*")

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 读取与 chat.py 同目录下的 config.ini
cfg = configparser.ConfigParser()
cfg.read(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini"), encoding="utf-8")
base_url = cfg["llm"]["base_url"].strip().rstrip("/")
api_key = cfg["llm"]["api_key"].strip()
model = cfg["llm"]["model"].strip()

history = []  # 存已完成的问答，每一轮都把全部历史一起发给模型

try:
    while True:
        prompt = input("please input your prompt: ")
        print("---")

        try:
            resp = requests.post(
                base_url + "/chat/completions",
                headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
                json={"model": model, "messages": history + [{"role": "user", "content": prompt}], "stream": True},
                stream=True,
                timeout=60,
            )
            if resp.status_code != 200:
                print("HTTP %s: %s" % (resp.status_code, resp.text[:300]))
                sys.exit(1)
            # SSE 响应头不带 charset，requests 会按 ISO-8859-1 解码，这里强制用 UTF-8，否则中文乱码
            resp.encoding = "utf-8"
            reply = []
            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    delta = json.loads(data)["choices"][0]["delta"].get("content")
                except (ValueError, KeyError, IndexError):
                    continue
                if delta:
                    print(delta, end="", flush=True)
                    reply.append(delta)
            print()
            history.append({"role": "user", "content": prompt})
            history.append({"role": "assistant", "content": "".join(reply)})
        except requests.RequestException as e:
            print("请求失败：%s" % e)
            sys.exit(1)
except KeyboardInterrupt:
    print()
