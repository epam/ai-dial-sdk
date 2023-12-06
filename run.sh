# curl -X POST -H "Api-Key: TEST" -d '{"messages": []}' http://127.0.0.1:5000/openai/deployments/echo/chat/completions

curl -X POST -H "Api-Key: TEST" -d '{"requests": []}' http://127.0.0.1:5000/openai/deployments/echo/tokenize