import requests, json

resp = requests.post(
    "http://localhost:11434/api/generate",
    json={
        "model": "llama3",
        "prompt": "Hello Ollama, just say hi."
    },
    stream=True  # important: stream mode
)

output = ""
for line in resp.iter_lines():
    if line:
        obj = json.loads(line.decode("utf-8"))
        output += obj.get("response", "")
        if obj.get("done", False):
            break

print("Final response:", output)
