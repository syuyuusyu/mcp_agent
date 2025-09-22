import json, subprocess, sys, re
from pathlib import Path

def main():
    data = subprocess.check_output(
        [sys.executable, "-m", "pipdeptree", "--warn", "silence", "--json"]
    )
    nodes = json.loads(data)
    name_to_children = {n["package"]["key"]: [c["key"] for c in n.get("dependencies", [])] for n in nodes}
    all_deps = set()
    for children in name_to_children.values():
        all_deps.update(children)
    roots = sorted(set(name_to_children.keys()) - all_deps)

    # 可能出现的“技术/底层”包，通常不需要写进顶层
    auto_exclude_regex = re.compile(r"^(typing-|charset-|idna$|six$|anyio$|sniffio$|h11$|packaging$|regex$|urllib3$|certifi$)")
    candidates = [r for r in roots if not auto_exclude_regex.search(r)]

    print("# 自动推导候选顶层依赖（请人工再精简/补充）")
    for r in candidates:
        print(r)

if __name__ == "__main__":
    main()