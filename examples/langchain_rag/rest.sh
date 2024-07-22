curl "http://localhost:5005/openai/deployments/simple-rag/chat/completions" \
  -X POST \
  -H "Content-Type: application:json" \
  -H "api-key:6ad6d1b74e3b4793a8437947aa444279" \
  -d '{
  "stream": false,
  "messages": [
    {
      "role": "user",
      "content": "Who is Miss Meyers?",
      "custom_content": {
        "attachments": [
          {
            "url": "https://en.wikipedia.org/wiki/Miss_Meyers"
          }
        ]
      }
    }
  ]
}'