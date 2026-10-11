OUT = []

def p(*a):
    s = " ".join(str(x) for x in a)
    OUT.append(s)
    print(s)

def publish():
    text = "\n".join(OUT)
    for i in range(0, min(len(text), 36000), 3500):
        chunk = text[i:i + 3500].replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::notice title=probe-output-{i // 3500:02d}::" + chunk)
