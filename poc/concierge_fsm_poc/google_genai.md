The Gemini API can generate text output from text, images, video, and audio
inputs.

Here's a basic example:

### Python

    from google import genai

    client = genai.Client()

    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents="How does AI work?"
    )
    print(response.text)

### JavaScript

    import { GoogleGenAI } from "@google/genai";

    const ai = new GoogleGenAI({});

    async function main() {
      const response = await ai.models.generateContent({
        model: "gemini-3-flash-preview",
        contents: "How does AI work?",
      });
      console.log(response.text);
    }

    await main();

### Go

    package main

    import (
      "context"
      "fmt"
      "os"
      "google.golang.org/genai"
    )

    func main() {

      ctx := context.Background()
      client, err := genai.NewClient(ctx, nil)
      if err != nil {
          log.Fatal(err)
      }

      result, _ := client.Models.GenerateContent(
          ctx,
          "gemini-3-flash-preview",
          genai.Text("Explain how AI works in a few words"),
          nil,
      )

      fmt.Println(result.Text())
    }

### Java

    import com.google.genai.Client;
    import com.google.genai.types.GenerateContentResponse;

    public class GenerateContentWithTextInput {
      public static void main(String[] args) {

        Client client = new Client();

        GenerateContentResponse response =
            client.models.generateContent("gemini-3-flash-preview", "How does AI work?", null);

        System.out.println(response.text());
      }
    }

### REST

    curl "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent" \
      -H "x-goog-api-key: $GEMINI_API_KEY" \
      -H 'Content-Type: application/json' \
      -X POST \
      -d '{
        "contents": [
          {
            "parts": [
              {
                "text": "How does AI work?"
              }
            ]
          }
        ]
      }'

### Apps Script

    // See https://developers.google.com/apps-script/guides/properties
    // for instructions on how to set the API key.
    const apiKey = PropertiesService.getScriptProperties().getProperty('GEMINI_API_KEY');

    function main() {
      const payload = {
        contents: [
          {
            parts: [
              { text: 'How AI does work?' },
            ],
          },
        ],
      };

      const url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent';
      const options = {
        method: 'POST',
        contentType: 'application/json',
        headers: {
          'x-goog-api-key': apiKey,
        },
        payload: JSON.stringify(payload)
      };

      const response = UrlFetchApp.fetch(url, options);
      const data = JSON.parse(response);
      const content = data['candidates'][0]['content']['parts'][0]['text'];
      console.log(content);
    }

## Thinking with Gemini

Gemini models often have ["thinking"](https://ai.google.dev/gemini-api/docs/thinking) enabled by default
which allows the model to reason before responding to a request.

Each model supports different thinking configurations which gives you control
over cost, latency, and intelligence. For more details, see the
[thinking guide](https://ai.google.dev/gemini-api/docs/thinking#set-budget).

### Python

    from google import genai
    from google.genai import types

    client = genai.Client()

    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents="How does AI work?",
        config=types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_level="low")
        ),
    )
    print(response.text)

### JavaScript

    import { GoogleGenAI, ThinkingLevel } from "@google/genai";

    const ai = new GoogleGenAI({});

    async function main() {
      const response = await ai.models.generateContent({
        model: "gemini-3-flash-preview",
        contents: "How does AI work?",
        config: {
          thinkingConfig: {
            thinkingLevel: ThinkingLevel.LOW,
          },
        }
      });
      console.log(response.text);
    }

    await main();

### Go

    package main

    import (
      "context"
      "fmt"
      "os"
      "google.golang.org/genai"
    )

    func main() {

      ctx := context.Background()
      client, err := genai.NewClient(ctx, nil)
      if err != nil {
          log.Fatal(err)
      }

      thinkingLevelVal := "low"

      result, _ := client.Models.GenerateContent(
          ctx,
          "gemini-3-flash-preview",
          genai.Text("How does AI work?"),
          &genai.GenerateContentConfig{
            ThinkingConfig: &genai.ThinkingConfig{
                ThinkingLevel: &thinkingLevelVal,
            },
          }
      )

      fmt.Println(result.Text())
    }

### Java

    import com.google.genai.Client;
    import com.google.genai.types.GenerateContentConfig;
    import com.google.genai.types.GenerateContentResponse;
    import com.google.genai.types.ThinkingConfig;
    import com.google.genai.types.ThinkingLevel;

    public class GenerateContentWithThinkingConfig {
      public static void main(String[] args) {

        Client client = new Client();

        GenerateContentConfig config =
            GenerateContentConfig.builder()
                .thinkingConfig(ThinkingConfig.builder().thinkingLevel(new ThinkingLevel("low")))
                .build();

        GenerateContentResponse response =
            client.models.generateContent("gemini-3-flash-preview", "How does AI work?", config);

        System.out.println(response.text());
      }
    }

### REST

    curl "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent" \
      -H "x-goog-api-key: $GEMINI_API_KEY" \
      -H 'Content-Type: application/json' \
      -X POST \
      -d '{
        "contents": [
          {
            "parts": [
              {
                "text": "How does AI work?"
              }
            ]
          }
        ],
        "generationConfig": {
          "thinkingConfig": {
            "thinkingLevel": "low"
          }
        }
      }'

### Apps Script

    // See https://developers.google.com/apps-script/guides/properties
    // for instructions on how to set the API key.
    const apiKey = PropertiesService.getScriptProperties().getProperty('GEMINI_API_KEY');

    function main() {
      const payload = {
        contents: [
          {
            parts: [
              { text: 'How AI does work?' },
            ],
          },
        ],
        generationConfig: {
          thinkingConfig: {
            thinkingLevel: 'low'
          }
        }
      };

      const url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent';
      const options = {
        method: 'POST',
        contentType: 'application/json',
        headers: {
          'x-goog-api-key': apiKey,
        },
        payload: JSON.stringify(payload)
      };

      const response = UrlFetchApp.fetch(url, options);
      const data = JSON.parse(response);
      const content = data['candidates'][0]['content']['parts'][0]['text'];
      console.log(content);
    }

## System instructions and other configurations

You can guide the behavior of Gemini models with system instructions. To do so,
pass a [`GenerateContentConfig`](https://ai.google.dev/api/generate-content#v1beta.GenerationConfig)
object.

### Python

    from google import genai
    from google.genai import types

    client = genai.Client()

    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        config=types.GenerateContentConfig(
            system_instruction="You are a cat. Your name is Neko."),
        contents="Hello there"
    )

    print(response.text)

### JavaScript

    import { GoogleGenAI } from "@google/genai";

    const ai = new GoogleGenAI({});

    async function main() {
      const response = await ai.models.generateContent({
        model: "gemini-3-flash-preview",
        contents: "Hello there",
        config: {
          systemInstruction: "You are a cat. Your name is Neko.",
        },
      });
      console.log(response.text);
    }

    await main();

### Go

    package main

    import (
      "context"
      "fmt"
      "os"
      "google.golang.org/genai"
    )

    func main() {

      ctx := context.Background()
      client, err := genai.NewClient(ctx, nil)
      if err != nil {
          log.Fatal(err)
      }

      config := &genai.GenerateContentConfig{
          SystemInstruction: genai.NewContentFromText("You are a cat. Your name is Neko.", genai.RoleUser),
      }

      result, _ := client.Models.GenerateContent(
          ctx,
          "gemini-3-flash-preview",
          genai.Text("Hello there"),
          config,
      )

      fmt.Println(result.Text())
    }

### Java

    import com.google.genai.Client;
    import com.google.genai.types.Content;
    import com.google.genai.types.GenerateContentConfig;
    import com.google.genai.types.GenerateContentResponse;
    import com.google.genai.types.Part;

    public class GenerateContentWithSystemInstruction {
      public static void main(String[] args) {

        Client client = new Client();

        GenerateContentConfig config =
            GenerateContentConfig.builder()
                .systemInstruction(
                    Content.fromParts(Part.fromText("You are a cat. Your name is Neko.")))
                .build();

        GenerateContentResponse response =
            client.models.generateContent("gemini-3-flash-preview", "Hello there", config);

        System.out.println(response.text());
      }
    }

### REST

    curl "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent" \
      -H "x-goog-api-key: $GEMINI_API_KEY" \
      -H 'Content-Type: application/json' \
      -d '{
        "system_instruction": {
          "parts": [
            {
              "text": "You are a cat. Your name is Neko."
            }
          ]
        },
        "contents": [
          {
            "parts": [
              {
                "text": "Hello there"
              }
            ]
          }
        ]
      }'

### Apps Script

    // See https://developers.google.com/apps-script/guides/properties
    // for instructions on how to set the API key.
    const apiKey = PropertiesService.getScriptProperties().getProperty('GEMINI_API_KEY');

    function main() {
      const systemInstruction = {
        parts: [{
          text: 'You are a cat. Your name is Neko.'
        }]
      };

      const payload = {
        systemInstruction,
        contents: [
          {
            parts: [
              { text: 'Hello there' },
            ],
          },
        ],
      };

      const url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent';
      const options = {
        method: 'POST',
        contentType: 'application/json',
        headers: {
          'x-goog-api-key': apiKey,
        },
        payload: JSON.stringify(payload)
      };

      const response = UrlFetchApp.fetch(url, options);
      const data = JSON.parse(response);
      const content = data['candidates'][0]['content']['parts'][0]['text'];
      console.log(content);
    }

The [`GenerateContentConfig`](https://ai.google.dev/api/generate-content#v1beta.GenerationConfig)
object also lets you override default generation parameters, such as
[temperature](https://ai.google.dev/api/generate-content#v1beta.GenerationConfig).
When using Gemini 3 models, we strongly recommend keeping the `temperature` at its default value of 1.0. Changing the temperature (setting it below 1.0) may lead to unexpected behavior, such as looping or degraded performance, particularly in complex mathematical or reasoning tasks.

### Python

    from google import genai
    from google.genai import types

    client = genai.Client()

    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=["Explain how AI works"],
        config=types.GenerateContentConfig(
            temperature=0.1
        )
    )
    print(response.text)

### JavaScript

    import { GoogleGenAI } from "@google/genai";

    const ai = new GoogleGenAI({});

    async function main() {
      const response = await ai.models.generateContent({
        model: "gemini-3-flash-preview",
        contents: "Explain how AI works",
        config: {
          temperature: 0.1,
        },
      });
      console.log(response.text);
    }

    await main();

### Go

    package main

    import (
      "context"
      "fmt"
      "os"
      "google.golang.org/genai"
    )

    func main() {

      ctx := context.Background()
      client, err := genai.NewClient(ctx, nil)
      if err != nil {
          log.Fatal(err)
      }

      temp := float32(0.9)
      topP := float32(0.5)
      topK := float32(20.0)

      config := &genai.GenerateContentConfig{
        Temperature:       &temp,
        TopP:              &topP,
        TopK:              &topK,
        ResponseMIMEType:  "application/json",
      }

      result, _ := client.Models.GenerateContent(
        ctx,
        "gemini-3-flash-preview",
        genai.Text("What is the average size of a swallow?"),
        config,
      )

      fmt.Println(result.Text())
    }

### Java

    import com.google.genai.Client;
    import com.google.genai.types.GenerateContentConfig;
    import com.google.genai.types.GenerateContentResponse;

    public class GenerateContentWithConfig {
      public static void main(String[] args) {

        Client client = new Client();

        GenerateContentConfig config = GenerateContentConfig.builder().temperature(0.1f).build();

        GenerateContentResponse response =
            client.models.generateContent("gemini-3-flash-preview", "Explain how AI works", config);

        System.out.println(response.text());
      }
    }

### REST

    curl https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent \
      -H "x-goog-api-key: $GEMINI_API_KEY" \
      -H 'Content-Type: application/json' \
      -X POST \
      -d '{
        "contents": [
          {
            "parts": [
              {
                "text": "Explain how AI works"
              }
            ]
          }
        ],
        "generationConfig": {
          "stopSequences": [
            "Title"
          ],
          "temperature": 1.0,
          "topP": 0.8,
          "topK": 10
        }
      }'

### Apps Script

    // See https://developers.google.com/apps-script/guides/properties
    // for instructions on how to set the API key.
    const apiKey = PropertiesService.getScriptProperties().getProperty('GEMINI_API_KEY');

    function main() {
      const generationConfig = {
        temperature: 1,
        topP: 0.95,
        topK: 40,
        responseMimeType: 'text/plain',
      };

      const payload = {
        generationConfig,
        contents: [
          {
            parts: [
              { text: 'Explain how AI works in a few words' },
            ],
          },
        ],
      };

      const url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent';
      const options = {
        method: 'POST',
        contentType: 'application/json',
        headers: {
          'x-goog-api-key': apiKey,
        },
        payload: JSON.stringify(payload)
      };

      const response = UrlFetchApp.fetch(url, options);
      const data = JSON.parse(response);
      const content = data['candidates'][0]['content']['parts'][0]['text'];
      console.log(content);
    }

Refer to the [`GenerateContentConfig`](https://ai.google.dev/api/generate-content#v1beta.GenerationConfig)
in our API reference for a complete list of configurable parameters and their
descriptions.

## Multimodal inputs

The Gemini API supports multimodal inputs, allowing you to combine text with
media files. The following example demonstrates providing an image:

### Python

    from PIL import Image
    from google import genai

    client = genai.Client()

    image = Image.open("/path/to/organ.png")
    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=[image, "Tell me about this instrument"]
    )
    print(response.text)

### JavaScript

    import {
      GoogleGenAI,
      createUserContent,
      createPartFromUri,
    } from "@google/genai";

    const ai = new GoogleGenAI({});

    async function main() {
      const image = await ai.files.upload({
        file: "/path/to/organ.png",
      });
      const response = await ai.models.generateContent({
        model: "gemini-3-flash-preview",
        contents: [
          createUserContent([
            "Tell me about this instrument",
            createPartFromUri(image.uri, image.mimeType),
          ]),
        ],
      });
      console.log(response.text);
    }

    await main();

### Go

    package main

    import (
      "context"
      "fmt"
      "os"
      "google.golang.org/genai"
    )

    func main() {

      ctx := context.Background()
      client, err := genai.NewClient(ctx, nil)
      if err != nil {
          log.Fatal(err)
      }

      imagePath := "/path/to/organ.jpg"
      imgData, _ := os.ReadFile(imagePath)

      parts := []*genai.Part{
          genai.NewPartFromText("Tell me about this instrument"),
          &genai.Part{
              InlineData: &genai.Blob{
                  MIMEType: "image/jpeg",
                  Data:     imgData,
              },
          },
      }

      contents := []*genai.Content{
          genai.NewContentFromParts(parts, genai.RoleUser),
      }

      result, _ := client.Models.GenerateContent(
          ctx,
          "gemini-3-flash-preview",
          contents,
          nil,
      )

      fmt.Println(result.Text())
    }

### Java

    import com.google.genai.Client;
    import com.google.genai.Content;
    import com.google.genai.types.GenerateContentResponse;
    import com.google.genai.types.Part;

    public class GenerateContentWithMultiModalInputs {
      public static void main(String[] args) {

        Client client = new Client();

        Content content =
          Content.fromParts(
              Part.fromText("Tell me about this instrument"),
              Part.fromUri("/path/to/organ.jpg", "image/jpeg"));

        GenerateContentResponse response =
            client.models.generateContent("gemini-3-flash-preview", content, null);

        System.out.println(response.text());
      }
    }

### REST

    # Use a temporary file to hold the base64 encoded image data
    TEMP_B64=$(mktemp)
    trap 'rm -f "$TEMP_B64"' EXIT
    base64 $B64FLAGS $IMG_PATH > "$TEMP_B64"

    # Use a temporary file to hold the JSON payload
    TEMP_JSON=$(mktemp)
    trap 'rm -f "$TEMP_JSON"' EXIT

    cat > "$TEMP_JSON" << EOF
    {
      "contents": [
        {
          "parts": [
            {
              "text": "Tell me about this instrument"
            },
            {
              "inline_data": {
                "mime_type": "image/jpeg",
                "data": "$(cat "$TEMP_B64")"
              }
            }
          ]
        }
      ]
    }
    EOF

    curl "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent" \
      -H "x-goog-api-key: $GEMINI_API_KEY" \
      -H 'Content-Type: application/json' \
      -X POST \
      -d "@$TEMP_JSON"

### Apps Script

    // See https://developers.google.com/apps-script/guides/properties
    // for instructions on how to set the API key.
    const apiKey = PropertiesService.getScriptProperties().getProperty('GEMINI_API_KEY');

    function main() {
      const imageUrl = 'http://image/url';
      const image = getImageData(imageUrl);
      const payload = {
        contents: [
          {
            parts: [
              { image },
              { text: 'Tell me about this instrument' },
            ],
          },
        ],
      };

      const url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent';
      const options = {
        method: 'POST',
        contentType: 'application/json',
        headers: {
          'x-goog-api-key': apiKey,
        },
        payload: JSON.stringify(payload)
      };

      const response = UrlFetchApp.fetch(url, options);
      const data = JSON.parse(response);
      const content = data['candidates'][0]['content']['parts'][0]['text'];
      console.log(content);
    }

    function getImageData(url) {
      const blob = UrlFetchApp.fetch(url).getBlob();

      return {
        mimeType: blob.getContentType(),
        data: Utilities.base64Encode(blob.getBytes())
      };
    }

For alternative methods of providing images and more advanced image processing,
see our [image understanding guide](https://ai.google.dev/gemini-api/docs/image-understanding).
The API also supports [document](https://ai.google.dev/gemini-api/docs/document-processing), [video](https://ai.google.dev/gemini-api/docs/video-understanding), and [audio](https://ai.google.dev/gemini-api/docs/audio)
inputs and understanding.

## Streaming responses

By default, the model returns a response only after the entire generation
process is complete.

For more fluid interactions, use streaming to receive [`GenerateContentResponse`](https://ai.google.dev/api/generate-content#v1beta.GenerateContentResponse) instances incrementally
as they're generated.

### Python

    from google import genai

    client = genai.Client()

    response = client.models.generate_content_stream(
        model="gemini-3-flash-preview",
        contents=["Explain how AI works"]
    )
    for chunk in response:
        print(chunk.text, end="")

### JavaScript

    import { GoogleGenAI } from "@google/genai";

    const ai = new GoogleGenAI({});

    async function main() {
      const response = await ai.models.generateContentStream({
        model: "gemini-3-flash-preview",
        contents: "Explain how AI works",
      });

      for await (const chunk of response) {
        console.log(chunk.text);
      }
    }

    await main();

### Go

    package main

    import (
      "context"
      "fmt"
      "os"
      "google.golang.org/genai"
    )

    func main() {

      ctx := context.Background()
      client, err := genai.NewClient(ctx, nil)
      if err != nil {
          log.Fatal(err)
      }

      stream := client.Models.GenerateContentStream(
          ctx,
          "gemini-3-flash-preview",
          genai.Text("Write a story about a magic backpack."),
          nil,
      )

      for chunk, _ := range stream {
          part := chunk.Candidates[0].Content.Parts[0]
          fmt.Print(part.Text)
      }
    }

### Java

    import com.google.genai.Client;
    import com.google.genai.ResponseStream;
    import com.google.genai.types.GenerateContentResponse;

    public class GenerateContentStream {
      public static void main(String[] args) {

        Client client = new Client();

        ResponseStream<GenerateContentResponse> responseStream =
          client.models.generateContentStream(
              "gemini-3-flash-preview", "Write a story about a magic backpack.", null);

        for (GenerateContentResponse res : responseStream) {
          System.out.print(res.text());
        }

        // To save resources and avoid connection leaks, it is recommended to close the response
        // stream after consumption (or using try block to get the response stream).
        responseStream.close();
      }
    }

### REST

    curl "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:streamGenerateContent?alt=sse" \
      -H "x-goog-api-key: $GEMINI_API_KEY" \
      -H 'Content-Type: application/json' \
      --no-buffer \
      -d '{
        "contents": [
          {
            "parts": [
              {
                "text": "Explain how AI works"
              }
            ]
          }
        ]
      }'

### Apps Script

    // See https://developers.google.com/apps-script/guides/properties
    // for instructions on how to set the API key.
    const apiKey = PropertiesService.getScriptProperties().getProperty('GEMINI_API_KEY');

    function main() {
      const payload = {
        contents: [
          {
            parts: [
              { text: 'Explain how AI works' },
            ],
          },
        ],
      };

      const url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:streamGenerateContent';
      const options = {
        method: 'POST',
        contentType: 'application/json',
        headers: {
          'x-goog-api-key': apiKey,
        },
        payload: JSON.stringify(payload)
      };

      const response = UrlFetchApp.fetch(url, options);
      const data = JSON.parse(response);
      const content = data['candidates'][0]['content']['parts'][0]['text'];
      console.log(content);
    }

## Multi-turn conversations (chat)

Our SDKs provide functionality to collect multiple rounds of prompts and
responses into a chat, giving you an easy way to keep track of the conversation
history.
**Note:** Chat functionality is only implemented as part of the SDKs. Behind the scenes, it still uses the [`generateContent`](https://ai.google.dev/api/generate-content#method:-models.generatecontent) API. For multi-turn conversations, the full conversation history is sent to the model with each follow-up turn.

### Python

    from google import genai

    client = genai.Client()
    chat = client.chats.create(model="gemini-3-flash-preview")

    response = chat.send_message("I have 2 dogs in my house.")
    print(response.text)

    response = chat.send_message("How many paws are in my house?")
    print(response.text)

    for message in chat.get_history():
        print(f'role - {message.role}',end=": ")
        print(message.parts[0].text)

### JavaScript

    import { GoogleGenAI } from "@google/genai";

    const ai = new GoogleGenAI({});

    async function main() {
      const chat = ai.chats.create({
        model: "gemini-3-flash-preview",
        history: [
          {
            role: "user",
            parts: [{ text: "Hello" }],
          },
          {
            role: "model",
            parts: [{ text: "Great to meet you. What would you like to know?" }],
          },
        ],
      });

      const response1 = await chat.sendMessage({
        message: "I have 2 dogs in my house.",
      });
      console.log("Chat response 1:", response1.text);

      const response2 = await chat.sendMessage({
        message: "How many paws are in my house?",
      });
      console.log("Chat response 2:", response2.text);
    }

    await main();

### Go

    package main

    import (
      "context"
      "fmt"
      "os"
      "google.golang.org/genai"
    )

    func main() {

      ctx := context.Background()
      client, err := genai.NewClient(ctx, nil)
      if err != nil {
          log.Fatal(err)
      }

      history := []*genai.Content{
          genai.NewContentFromText("Hi nice to meet you! I have 2 dogs in my house.", genai.RoleUser),
          genai.NewContentFromText("Great to meet you. What would you like to know?", genai.RoleModel),
      }

      chat, _ := client.Chats.Create(ctx, "gemini-3-flash-preview", nil, history)
      res, _ := chat.SendMessage(ctx, genai.Part{Text: "How many paws are in my house?"})

      if len(res.Candidates) > 0 {
          fmt.Println(res.Candidates[0].Content.Parts[0].Text)
      }
    }

### Java

    import com.google.genai.Chat;
    import com.google.genai.Client;
    import com.google.genai.types.Content;
    import com.google.genai.types.GenerateContentResponse;

    public class MultiTurnConversation {
      public static void main(String[] args) {

        Client client = new Client();
        Chat chatSession = client.chats.create("gemini-3-flash-preview");

        GenerateContentResponse response =
            chatSession.sendMessage("I have 2 dogs in my house.");
        System.out.println("First response: " + response.text());

        response = chatSession.sendMessage("How many paws are in my house?");
        System.out.println("Second response: " + response.text());

        // Get the history of the chat session.
        // Passing 'true' to getHistory() returns the curated history, which excludes
        // empty or invalid parts.
        // Passing 'false' here would return the comprehensive history, including
        // empty or invalid parts.
        ImmutableList<Content> history = chatSession.getHistory(true);
        System.out.println("History: " + history);
      }
    }

### REST

    curl https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent \
      -H "x-goog-api-key: $GEMINI_API_KEY" \
      -H 'Content-Type: application/json' \
      -X POST \
      -d '{
        "contents": [
          {
            "role": "user",
            "parts": [
              {
                "text": "Hello"
              }
            ]
          },
          {
            "role": "model",
            "parts": [
              {
                "text": "Great to meet you. What would you like to know?"
              }
            ]
          },
          {
            "role": "user",
            "parts": [
              {
                "text": "I have two dogs in my house. How many paws are in my house?"
              }
            ]
          }
        ]
      }'

### Apps Script

    // See https://developers.google.com/apps-script/guides/properties
    // for instructions on how to set the API key.
    const apiKey = PropertiesService.getScriptProperties().getProperty('GEMINI_API_KEY');

    function main() {
      const payload = {
        contents: [
          {
            role: 'user',
            parts: [
              { text: 'Hello' },
            ],
          },
          {
            role: 'model',
            parts: [
              { text: 'Great to meet you. What would you like to know?' },
            ],
          },
          {
            role: 'user',
            parts: [
              { text: 'I have two dogs in my house. How many paws are in my house?' },
            ],
          },
        ],
      };

      const url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent';
      const options = {
        method: 'POST',
        contentType: 'application/json',
        headers: {
          'x-goog-api-key': apiKey,
        },
        payload: JSON.stringify(payload)
      };

      const response = UrlFetchApp.fetch(url, options);
      const data = JSON.parse(response);
      const content = data['candidates'][0]['content']['parts'][0]['text'];
      console.log(content);
    }

Streaming can also be used for multi-turn conversations.

### Python

    from google import genai

    client = genai.Client()
    chat = client.chats.create(model="gemini-3-flash-preview")

    response = chat.send_message_stream("I have 2 dogs in my house.")
    for chunk in response:
        print(chunk.text, end="")

    response = chat.send_message_stream("How many paws are in my house?")
    for chunk in response:
        print(chunk.text, end="")

    for message in chat.get_history():
        print(f'role - {message.role}', end=": ")
        print(message.parts[0].text)

### JavaScript

    import { GoogleGenAI } from "@google/genai";

    const ai = new GoogleGenAI({});

    async function main() {
      const chat = ai.chats.create({
        model: "gemini-3-flash-preview",
        history: [
          {
            role: "user",
            parts: [{ text: "Hello" }],
          },
          {
            role: "model",
            parts: [{ text: "Great to meet you. What would you like to know?" }],
          },
        ],
      });

      const stream1 = await chat.sendMessageStream({
        message: "I have 2 dogs in my house.",
      });
      for await (const chunk of stream1) {
        console.log(chunk.text);
        console.log("_".repeat(80));
      }

      const stream2 = await chat.sendMessageStream({
        message: "How many paws are in my house?",
      });
      for await (const chunk of stream2) {
        console.log(chunk.text);
        console.log("_".repeat(80));
      }
    }

    await main();

### Go

    package main

    import (
      "context"
      "fmt"
      "os"
      "google.golang.org/genai"
    )

    func main() {

      ctx := context.Background()
      client, err := genai.NewClient(ctx, nil)
      if err != nil {
          log.Fatal(err)
      }

      history := []*genai.Content{
          genai.NewContentFromText("Hi nice to meet you! I have 2 dogs in my house.", genai.RoleUser),
          genai.NewContentFromText("Great to meet you. What would you like to know?", genai.RoleModel),
      }

      chat, _ := client.Chats.Create(ctx, "gemini-3-flash-preview", nil, history)
      stream := chat.SendMessageStream(ctx, genai.Part{Text: "How many paws are in my house?"})

      for chunk, _ := range stream {
          part := chunk.Candidates[0].Content.Parts[0]
          fmt.Print(part.Text)
      }
    }

### Java

    import com.google.genai.Chat;
    import com.google.genai.Client;
    import com.google.genai.ResponseStream;
    import com.google.genai.types.GenerateContentResponse;

    public class MultiTurnConversationWithStreaming {
      public static void main(String[] args) {

        Client client = new Client();
        Chat chatSession = client.chats.create("gemini-3-flash-preview");

        ResponseStream<GenerateContentResponse> responseStream =
            chatSession.sendMessageStream("I have 2 dogs in my house.", null);

        for (GenerateContentResponse response : responseStream) {
          System.out.print(response.text());
        }

        responseStream = chatSession.sendMessageStream("How many paws are in my house?", null);

        for (GenerateContentResponse response : responseStream) {
          System.out.print(response.text());
        }

        // Get the history of the chat session. History is added after the stream
        // is consumed and includes the aggregated response from the stream.
        System.out.println("History: " + chatSession.getHistory(false));
      }
    }

### REST

    curl https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:streamGenerateContent?alt=sse \
      -H "x-goog-api-key: $GEMINI_API_KEY" \
      -H 'Content-Type: application/json' \
      -X POST \
      -d '{
        "contents": [
          {
            "role": "user",
            "parts": [
              {
                "text": "Hello"
              }
            ]
          },
          {
            "role": "model",
            "parts": [
              {
                "text": "Great to meet you. What would you like to know?"
              }
            ]
          },
          {
            "role": "user",
            "parts": [
              {
                "text": "I have two dogs in my house. How many paws are in my house?"
              }
            ]
          }
        ]
      }'

### Apps Script

    // See https://developers.google.com/apps-script/guides/properties
    // for instructions on how to set the API key.
    const apiKey = PropertiesService.getScriptProperties().getProperty('GEMINI_API_KEY');

    function main() {
      const payload = {
        contents: [
          {
            role: 'user',
            parts: [
              { text: 'Hello' },
            ],
          },
          {
            role: 'model',
            parts: [
              { text: 'Great to meet you. What would you like to know?' },
            ],
          },
          {
            role: 'user',
            parts: [
              { text: 'I have two dogs in my house. How many paws are in my house?' },
            ],
          },
        ],
      };

      const url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:streamGenerateContent';
      const options = {
        method: 'POST',
        contentType: 'application/json',
        headers: {
          'x-goog-api-key': apiKey,
        },
        payload: JSON.stringify(payload)
      };

      const response = UrlFetchApp.fetch(url, options);
      const data = JSON.parse(response);
      const content = data['candidates'][0]['content']['parts'][0]['text'];
      console.log(content);
    }

## Prompting tips

Consult our [prompt engineering guide](https://ai.google.dev/gemini/docs/prompting-strategies) for
suggestions on getting the most out of Gemini.

## What's next

- Try [Gemini in Google AI Studio](https://aistudio.google.com).
- Experiment with [structured outputs](https://ai.google.dev/gemini-api/docs/structured-output) for JSON-like responses.
- Explore Gemini's [image](https://ai.google.dev/gemini-api/docs/image-understanding), [video](https://ai.google.dev/gemini-api/docs/video-understanding), [audio](https://ai.google.dev/gemini-api/docs/audio) and [document](https://ai.google.dev/gemini-api/docs/document-processing) understanding capabilities.
- Learn about multimodal [file prompting strategies](https://ai.google.dev/gemini-api/docs/files#prompt-guide).

<br />

The [Gemini 3 and 2.5 series models](https://ai.google.dev/gemini-api/docs/models) use an internal
"thinking process" that significantly improves their reasoning and multi-step
planning abilities, making them highly effective for complex tasks such as
coding, advanced mathematics, and data analysis.

This guide shows you how to work with Gemini's thinking capabilities using the
Gemini API.

## Generating content with thinking

Initiating a request with a thinking model is similar to any other content
generation request. The key difference lies in specifying one of the
[models with thinking support](https://ai.google.dev/gemini-api/docs/thinking#supported-models) in the `model` field, as
demonstrated in the following [text generation](https://ai.google.dev/gemini-api/docs/text-generation#text-input) example:

### Python

    from google import genai

    client = genai.Client()
    prompt = "Explain the concept of Occam's Razor and provide a simple, everyday example."
    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=prompt
    )

    print(response.text)

### JavaScript

    import { GoogleGenAI } from "@google/genai";

    const ai = new GoogleGenAI({});

    async function main() {
      const prompt = "Explain the concept of Occam's Razor and provide a simple, everyday example.";

      const response = await ai.models.generateContent({
        model: "gemini-3-flash-preview",
        contents: prompt,
      });

      console.log(response.text);
    }

    main();

### Go

    package main

    import (
      "context"
      "fmt"
      "log"
      "os"
      "google.golang.org/genai"
    )

    func main() {
      ctx := context.Background()
      client, err := genai.NewClient(ctx, nil)
      if err != nil {
          log.Fatal(err)
      }

      prompt := "Explain the concept of Occam's Razor and provide a simple, everyday example."
      model := "gemini-3-flash-preview"

      resp, _ := client.Models.GenerateContent(ctx, model, genai.Text(prompt), nil)

      fmt.Println(resp.Text())
    }

### REST

    curl "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent" \
     -H "x-goog-api-key: $GEMINI_API_KEY" \
     -H 'Content-Type: application/json' \
     -X POST \
     -d '{
       "contents": [
         {
           "parts": [
             {
               "text": "Explain the concept of Occam'\''s Razor and provide a simple, everyday example."
             }
           ]
         }
       ]
     }'
     ```

## Thought summaries

Thought summaries are summarized versions of the model's raw thoughts and offer
insights into the model's internal reasoning process. Note that
thinking levels and budgets apply to the model's raw thoughts and not to thought
summaries.

You can enable thought summaries by setting `includeThoughts` to `true` in your
request configuration. You can then access the summary by iterating through the
`response` parameter's `parts`, and checking the `thought` boolean.

Here's an example demonstrating how to enable and retrieve thought summaries
without streaming, which returns a single, final thought summary with the
response:

### Python

    from google import genai
    from google.genai import types

    client = genai.Client()
    prompt = "What is the sum of the first 50 prime numbers?"
    response = client.models.generate_content(
      model="gemini-3-flash-preview",
      contents=prompt,
      config=types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(
          include_thoughts=True
        )
      )
    )

    for part in response.candidates[0].content.parts:
      if not part.text:
        continue
      if part.thought:
        print("Thought summary:")
        print(part.text)
        print()
      else:
        print("Answer:")
        print(part.text)
        print()

### JavaScript

    import { GoogleGenAI } from "@google/genai";

    const ai = new GoogleGenAI({});

    async function main() {
      const response = await ai.models.generateContent({
        model: "gemini-3-flash-preview",
        contents: "What is the sum of the first 50 prime numbers?",
        config: {
          thinkingConfig: {
            includeThoughts: true,
          },
        },
      });

      for (const part of response.candidates[0].content.parts) {
        if (!part.text) {
          continue;
        }
        else if (part.thought) {
          console.log("Thoughts summary:");
          console.log(part.text);
        }
        else {
          console.log("Answer:");
          console.log(part.text);
        }
      }
    }

    main();

### Go

    package main

    import (
      "context"
      "fmt"
      "google.golang.org/genai"
      "os"
    )

    func main() {
      ctx := context.Background()
      client, err := genai.NewClient(ctx, nil)
      if err != nil {
          log.Fatal(err)
      }

      contents := genai.Text("What is the sum of the first 50 prime numbers?")
      model := "gemini-3-flash-preview"
      resp, _ := client.Models.GenerateContent(ctx, model, contents, &genai.GenerateContentConfig{
        ThinkingConfig: &genai.ThinkingConfig{
          IncludeThoughts: true,
        },
      })

      for _, part := range resp.Candidates[0].Content.Parts {
        if part.Text != "" {
          if part.Thought {
            fmt.Println("Thoughts Summary:")
            fmt.Println(part.Text)
          } else {
            fmt.Println("Answer:")
            fmt.Println(part.Text)
          }
        }
      }
    }

And here is an example using thinking with streaming, which returns rolling,
incremental summaries during generation:

### Python

    from google import genai
    from google.genai import types

    client = genai.Client()

    prompt = """
    Alice, Bob, and Carol each live in a different house on the same street: red, green, and blue.
    The person who lives in the red house owns a cat.
    Bob does not live in the green house.
    Carol owns a dog.
    The green house is to the left of the red house.
    Alice does not own a cat.
    Who lives in each house, and what pet do they own?
    """

    thoughts = ""
    answer = ""

    for chunk in client.models.generate_content_stream(
        model="gemini-3-flash-preview",
        contents=prompt,
        config=types.GenerateContentConfig(
          thinking_config=types.ThinkingConfig(
            include_thoughts=True
          )
        )
    ):
      for part in chunk.candidates[0].content.parts:
        if not part.text:
          continue
        elif part.thought:
          if not thoughts:
            print("Thoughts summary:")
          print(part.text)
          thoughts += part.text
        else:
          if not answer:
            print("Answer:")
          print(part.text)
          answer += part.text

### JavaScript

    import { GoogleGenAI } from "@google/genai";

    const ai = new GoogleGenAI({});

    const prompt = `Alice, Bob, and Carol each live in a different house on the same
    street: red, green, and blue. The person who lives in the red house owns a cat.
    Bob does not live in the green house. Carol owns a dog. The green house is to
    the left of the red house. Alice does not own a cat. Who lives in each house,
    and what pet do they own?`;

    let thoughts = "";
    let answer = "";

    async function main() {
      const response = await ai.models.generateContentStream({
        model: "gemini-3-flash-preview",
        contents: prompt,
        config: {
          thinkingConfig: {
            includeThoughts: true,
          },
        },
      });

      for await (const chunk of response) {
        for (const part of chunk.candidates[0].content.parts) {
          if (!part.text) {
            continue;
          } else if (part.thought) {
            if (!thoughts) {
              console.log("Thoughts summary:");
            }
            console.log(part.text);
            thoughts = thoughts + part.text;
          } else {
            if (!answer) {
              console.log("Answer:");
            }
            console.log(part.text);
            answer = answer + part.text;
          }
        }
      }
    }

    await main();

### Go

    package main

    import (
      "context"
      "fmt"
      "log"
      "os"
      "google.golang.org/genai"
    )

    const prompt = `
    Alice, Bob, and Carol each live in a different house on the same street: red, green, and blue.
    The person who lives in the red house owns a cat.
    Bob does not live in the green house.
    Carol owns a dog.
    The green house is to the left of the red house.
    Alice does not own a cat.
    Who lives in each house, and what pet do they own?
    `

    func main() {
      ctx := context.Background()
      client, err := genai.NewClient(ctx, nil)
      if err != nil {
          log.Fatal(err)
      }

      contents := genai.Text(prompt)
      model := "gemini-3-flash-preview"

      resp := client.Models.GenerateContentStream(ctx, model, contents, &genai.GenerateContentConfig{
        ThinkingConfig: &genai.ThinkingConfig{
          IncludeThoughts: true,
        },
      })

      for chunk := range resp {
        for _, part := range chunk.Candidates[0].Content.Parts {
          if len(part.Text) == 0 {
            continue
          }

          if part.Thought {
            fmt.Printf("Thought: %s\n", part.Text)
          } else {
            fmt.Printf("Answer: %s\n", part.Text)
          }
        }
      }
    }

## Controlling thinking

Gemini models engage in dynamic thinking by default, automatically adjusting the
amount of reasoning effort based on the complexity of the user's request.
However, if you have specific latency constraints or require the model to engage
in deeper reasoning than usual, you can optionally use parameters to control
thinking behavior.

### Thinking levels (Gemini 3)

The `thinkingLevel` parameter, recommended for Gemini 3 models and onwards,
lets you control reasoning behavior.
You can set thinking level to `"low"` or `"high"` for Gemini 3 Pro, and
`"minimal"`, `"low"`, `"medium"`, and `"high"` for Gemini 3 Flash.

**Gemini 3 Pro and Flash thinking levels:**

- `low`: Minimizes latency and cost. Best for simple instruction following, chat, or high-throughput applications
- `high` (Default, dynamic): Maximizes reasoning depth. The model may take significantly longer to reach a first token, but the output will be more carefully reasoned.

**Gemini 3 Flash thinking levels**

In addition to the levels above, Gemini 3 Flash also supports the following
thinking levels that are not currently supported by Gemini 3 Pro:

- `medium`: Balanced thinking for most tasks.
- `minimal`: Matches the "no thinking" setting for most queries. The model may
  think very minimally for complex coding tasks. Minimizes latency for chat or
  high throughput applications.

  | **Note:** `minimal` does not guarantee that thinking is off.

### Python

    from google import genai
    from google.genai import types

    client = genai.Client()

    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents="Provide a list of 3 famous physicists and their key contributions",
        config=types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_level="low")
        ),
    )

    print(response.text)

### JavaScript

    import { GoogleGenAI, ThinkingLevel } from "@google/genai";

    const ai = new GoogleGenAI({});

    async function main() {
      const response = await ai.models.generateContent({
        model: "gemini-3-flash-preview",
        contents: "Provide a list of 3 famous physicists and their key contributions",
        config: {
          thinkingConfig: {
            thinkingLevel: ThinkingLevel.LOW,
          },
        },
      });

      console.log(response.text);
    }

    main();

### Go

    package main

    import (
      "context"
      "fmt"
      "google.golang.org/genai"
      "os"
    )

    func main() {
      ctx := context.Background()
      client, err := genai.NewClient(ctx, nil)
      if err != nil {
          log.Fatal(err)
      }

      thinkingLevelVal := "low"

      contents := genai.Text("Provide a list of 3 famous physicists and their key contributions")
      model := "gemini-3-flash-preview"
      resp, _ := client.Models.GenerateContent(ctx, model, contents, &genai.GenerateContentConfig{
        ThinkingConfig: &genai.ThinkingConfig{
          ThinkingLevel: &thinkingLevelVal,
        },
      })

    fmt.Println(resp.Text())
    }

### REST

    curl "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent" \
    -H "x-goog-api-key: $GEMINI_API_KEY" \
    -H 'Content-Type: application/json' \
    -X POST \
    -d '{
      "contents": [
        {
          "parts": [
            {
              "text": "Provide a list of 3 famous physicists and their key contributions"
            }
          ]
        }
      ],
      "generationConfig": {
        "thinkingConfig": {
              "thinkingLevel": "low"
        }
      }
    }'

You cannot disable thinking for Gemini 3 Pro. Gemini 3 Flash also does not
support full thinking-off, but the `minimal`
setting means the model likely will not think (though it still potentially can).
If you don't specify a thinking level, Gemini will use the Gemini 3 models'
default dynamic thinking level, `"high"`.

Gemini 2.5 series models don't support `thinkingLevel`; use `thinkingBudget`
instead.

### Thinking budgets

The `thinkingBudget` parameter, introduced with the Gemini 2.5 series, guides
the model on the specific number of thinking tokens to use for reasoning.
| **Note:** Use the `thinkingLevel` parameter with Gemini 3 models. While `thinkingBudget` is accepted for backwards compatibility, using it with Gemini 3 Pro may result in suboptimal performance.

The following are `thinkingBudget` configuration details for each model type.
You can disable thinking by setting `thinkingBudget` to 0.
Setting the `thinkingBudget` to -1 turns
on **dynamic thinking**, meaning the model will adjust the budget based on the
complexity of the request.

| Model | Default setting (Thinking budget is not set) | Range | Disable thinking | Turn on dynamic thinking |
|---|---|---|---|---|
| **2.5 Pro** | Dynamic thinking | `128` to `32768` | N/A: Cannot disable thinking | `thinkingBudget = -1` (Default) |
| **2.5 Flash** | Dynamic thinking | `0` to `24576` | `thinkingBudget = 0` | `thinkingBudget = -1` (Default) |
| **2.5 Flash Preview** | Dynamic thinking | `0` to `24576` | `thinkingBudget = 0` | `thinkingBudget = -1` (Default) |
| **2.5 Flash Lite** | Model does not think | `512` to `24576` | `thinkingBudget = 0` | `thinkingBudget = -1` |
| **2.5 Flash Lite Preview** | Model does not think | `512` to `24576` | `thinkingBudget = 0` | `thinkingBudget = -1` |
| **Robotics-ER 1.5 Preview** | Dynamic thinking | `0` to `24576` | `thinkingBudget = 0` | `thinkingBudget = -1` (Default) |
| **2.5 Flash Live Native Audio Preview (09-2025)** | Dynamic thinking | `0` to `24576` | `thinkingBudget = 0` | `thinkingBudget = -1` (Default) |

### Python

    from google import genai
    from google.genai import types

    client = genai.Client()

    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents="Provide a list of 3 famous physicists and their key contributions",
        config=types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_budget=1024)
            # Turn off thinking:
            # thinking_config=types.ThinkingConfig(thinking_budget=0)
            # Turn on dynamic thinking:
            # thinking_config=types.ThinkingConfig(thinking_budget=-1)
        ),
    )

    print(response.text)

### JavaScript

    import { GoogleGenAI } from "@google/genai";

    const ai = new GoogleGenAI({});

    async function main() {
      const response = await ai.models.generateContent({
        model: "gemini-3-flash-preview",
        contents: "Provide a list of 3 famous physicists and their key contributions",
        config: {
          thinkingConfig: {
            thinkingBudget: 1024,
            // Turn off thinking:
            // thinkingBudget: 0
            // Turn on dynamic thinking:
            // thinkingBudget: -1
          },
        },
      });

      console.log(response.text);
    }

    main();

### Go

    package main

    import (
      "context"
      "fmt"
      "google.golang.org/genai"
      "os"
    )

    func main() {
      ctx := context.Background()
      client, err := genai.NewClient(ctx, nil)
      if err != nil {
          log.Fatal(err)
      }

      thinkingBudgetVal := int32(1024)

      contents := genai.Text("Provide a list of 3 famous physicists and their key contributions")
      model := "gemini-3-flash-preview"
      resp, _ := client.Models.GenerateContent(ctx, model, contents, &genai.GenerateContentConfig{
        ThinkingConfig: &genai.ThinkingConfig{
          ThinkingBudget: &thinkingBudgetVal,
          // Turn off thinking:
          // ThinkingBudget: int32(0),
          // Turn on dynamic thinking:
          // ThinkingBudget: int32(-1),
        },
      })

    fmt.Println(resp.Text())
    }

### REST

    curl "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent" \
    -H "x-goog-api-key: $GEMINI_API_KEY" \
    -H 'Content-Type: application/json' \
    -X POST \
    -d '{
      "contents": [
        {
          "parts": [
            {
              "text": "Provide a list of 3 famous physicists and their key contributions"
            }
          ]
        }
      ],
      "generationConfig": {
        "thinkingConfig": {
              "thinkingBudget": 1024
        }
      }
    }'

Depending on the prompt, the model might overflow or underflow the token budget.

## Thought signatures

The Gemini API is stateless, so the model treats every API request independently
and doesn't have access to thought context from previous turns in multi-turn
interactions.

In order to enable maintaining thought context across multi-turn interactions,
Gemini returns thought signatures, which are encrypted representations of the
model's internal thought process.

- **Gemini 2.5 models** return thought signatures when thinking is enabled and the request includes [function calling](https://ai.google.dev/gemini-api/docs/function-calling#thinking), specifically [function declarations](https://ai.google.dev/gemini-api/docs/function-calling#step-2).
- **Gemini 3 models** may return thought signatures for all types of [parts](https://ai.google.dev/api/caching#Part).
  We recommend you always pass all signatures back as received, but it's
  *required* for function calling signatures. Read the
  [Thought Signatures](https://ai.google.dev/gemini-api/docs/thought-signatures) page to
  learn more.

  | **Note:** Circulation of thought signatures is required even when set to `minimal` for Gemini Flash 3.

The [Google GenAI SDK](https://ai.google.dev/gemini-api/docs/libraries) automatically handles the
return of thought signatures for you. You only need to
[manage thought signatures manually](https://ai.google.dev/gemini-api/docs/function-calling#thought-signatures)
if you're modifying conversation history or using the REST API.

Other usage limitations to consider with function calling include:

- Signatures are returned from the model within other parts in the response, for example function calling or text parts. [Return the entire response](https://ai.google.dev/gemini-api/docs/function-calling#step-4) with all parts back to the model in subsequent turns.
- Don't concatenate parts with signatures together.
- Don't merge one part with a signature with another part without a signature.

## Pricing

| **Note:** **Summaries** are available in the [free and paid tiers](https://ai.google.dev/gemini-api/docs/pricing) of the API. **Thought signatures** will increase the input tokens you are charged when sent back as part of the request.

When thinking is turned on, response pricing is the sum of output
tokens and thinking tokens. You can get the total number of generated thinking
tokens from the `thoughtsTokenCount` field.

### Python

    # ...
    print("Thoughts tokens:",response.usage_metadata.thoughts_token_count)
    print("Output tokens:",response.usage_metadata.candidates_token_count)

### JavaScript

    // ...
    console.log(`Thoughts tokens: ${response.usageMetadata.thoughtsTokenCount}`);
    console.log(`Output tokens: ${response.usageMetadata.candidatesTokenCount}`);

### Go

    // ...
    usageMetadata, err := json.MarshalIndent(response.UsageMetadata, "", "  ")
    if err != nil {
      log.Fatal(err)
    }
    fmt.Println("Thoughts tokens:", string(usageMetadata.thoughts_token_count))
    fmt.Println("Output tokens:", string(usageMetadata.candidates_token_count))

Thinking models generate full thoughts to improve the quality of the final
response, and then output [summaries](https://ai.google.dev/gemini-api/docs/thinking#summaries) to provide insight into the
thought process. So, pricing is based on the full thought tokens the
model needs to generate to create a summary, despite only the summary being
output from the API.

You can learn more about tokens in the [Token counting](https://ai.google.dev/gemini-api/docs/tokens)
guide.

## Best practices

This section includes some guidance for using thinking models efficiently.
As always, following our [prompting guidance and best practices](https://ai.google.dev/gemini-api/docs/prompting-strategies) will get you the best results.

### Debugging and steering

- **Review reasoning**: When you're not getting your expected response from the
  thinking models, it can help to carefully analyze Gemini's thought summaries.
  You can see how it broke down the task and arrived at its conclusion, and use
  that information to correct towards the right results.

- **Provide Guidance in Reasoning** : If you're hoping for a particularly lengthy
  output, you may want to provide guidance in your prompt to constrain the
  [amount of thinking](https://ai.google.dev/gemini-api/docs/thinking#set-budget) the model uses. This lets you reserve more
  of the token output for your response.

### Task complexity

- **Easy Tasks (Thinking could be OFF):** For straightforward requests where complex reasoning isn't required, such as fact retrieval or classification, thinking is not required. Examples include:
  - "Where was DeepMind founded?"
  - "Is this email asking for a meeting or just providing information?"
- **Medium Tasks (Default/Some Thinking):** Many common requests benefit from a degree of step-by-step processing or deeper understanding. Gemini can flexibly use thinking capability for tasks like:
  - Analogize photosynthesis and growing up.
  - Compare and contrast electric cars and hybrid cars.
- **Hard Tasks (Maximum Thinking Capability):** For truly complex challenges, such as solving complex math problems or coding tasks, we recommend setting a high thinking budget. These types of tasks require the model to engage its full reasoning and planning capabilities, often involving many internal steps before providing an answer. Examples include:
  - Solve problem 1 in AIME 2025: Find the sum of all integer bases b \> 9 for which 17~b~ is a divisor of 97~b~.
  - Write Python code for a web application that visualizes real-time stock market data, including user authentication. Make it as efficient as possible.

## Supported models, tools, and capabilities

Thinking features are supported on all 3 and 2.5 series models.
You can find all model capabilities on the
[model overview](https://ai.google.dev/gemini-api/docs/models) page.

Thinking models work with all of Gemini's tools and capabilities. This allows
the models to interact with external systems, execute code, or access real-time
information, incorporating the results into their reasoning and final response.

You can try examples of using tools with thinking models in the
[Thinking cookbook](https://colab.sandbox.google.com/github/google-gemini/cookbook/blob/main/quickstarts/Get_started_thinking.ipynb).

## What's next?

- Thinking coverage is available in our [OpenAI Compatibility](https://ai.google.dev/gemini-api/docs/openai#thinking) guide.

<br />

Thought signatures are encrypted representations of the model's internal thought process and are used to preserve reasoning context across multi-step interactions. When using thinking models (such as the Gemini 3 and 2.5 series), the API may return a`thoughtSignature`field within the[content parts](https://ai.google.dev/api/caching#Part)of the response (e.g.,`text`or`functionCall`parts).

As a general rule, if you receive a thought signature in a model response, you should pass it back exactly as received when sending the conversation history in the next turn.**When using Gemini 3 models, you must pass back thought signatures during function calling, otherwise you will get a validation error** (4xx status code). This includes when using the`minimal`[thinking level](https://ai.google.dev/gemini-api/docs/thinking#thinking-levels)setting for Gemini 3 Flash.
| **Note:** If you use the official[Google Gen AI SDKs](https://ai.google.dev/gemini-api/docs/libraries)and use the chat feature (or append the full model response object directly to history),**thought signatures are handled automatically**. You do not need to manually extract or manage them, or change your code.

## How it works

The graphic below visualizes the meaning of "turn" and "step" as they pertain to[function calling](https://ai.google.dev/gemini-api/docs/function-calling)in the Gemini API. A "turn" is a single, complete exchange in a conversation between a user and a model. A "step" is a finer-grained action or operation performed by the model, often as part of a larger process to complete a turn.

![Function calling turns and steps diagram](https://ai.google.dev/static/gemini-api/docs/images/fc-turns.png)

*This document focuses on handling function calling for Gemini 3 models. Refer to the[model behavior](https://ai.google.dev/gemini-api/docs/thought-signatures#model-behavior)section for discrepancies with 2.5.*

Gemini 3 returns thought signatures for all model responses (responses from the API) with a function call. Thought signatures show up in the following cases:

- When there are[parallel function](https://ai.google.dev/gemini-api/docs/function-calling#parallel_function_calling)calls, the first function call part returned by the model response will have a thought signature.
- When there are sequential function calls (multi-step), each function call will have a signature and you must pass all signatures back.
- Model responses without a function call will return a thought signature inside the last part returned by the model.

The following table provides a visualization for multi-step function calls, combining the definitions of turns and steps with the concept of signatures introduced above:

|----------|----------|-------------------------------------------------|---------------------------------|----------------------|
| **Turn** | **Step** | **User Request**                                | **Model Response**              | **FunctionResponse** |
| 1        | 1        | `request1 = user_prompt`                        | `FC1 + signature`               | `FR1`                |
| 1        | 2        | `request2 = request1 + (FC1 + signature) + FR1` | `FC2 + signature`               | `FR2`                |
| 1        | 3        | `request3 = request2 + (FC2 + signature) + FR2` | `text_output` <br /> `(no FCs)` | None                 |

## Signatures in function calling parts

When Gemini generates a`functionCall`, it relies on the`thought_signature`to process the tool's output correctly in the next turn.

- **Behavior** :
  - **Single Function Call** : The`functionCall`part will contain a`thought_signature`.
  - **Parallel Function Calls** : If the model generates parallel function calls in a response, the`thought_signature`is attached**only to the first** `functionCall`part. Subsequent`functionCall`parts in the same response will**not**contain a signature.
- **Requirement** : You**must**return this signature in the exact part where it was received when sending the conversation history back.
- **Validation** : Strict validation is enforced for all function calls within the current turn . (Only current turn is required; we don't validate on previous turns)
  - The API goes back in the history (newest to oldest) to find the most recent**User** message that contains standard content (e.g.,`text`) ( which would be the start of the current turn). This will not**be** a`functionResponse`.
  - **All** model`functionCall`turns occurring after that specific use message are considered part of the turn.
  - The**first** `functionCall`part in**each step** of the current turn**must** include its`thought_signature`.
  - If you omit a`thought_signature`for the first`functionCall`part in any step of the current turn, the request will fail with a 400 error.
- **If proper signatures are not returned, here is how you will error out**
  - `gemini-3-pro-preview`and`gemini-3-flash-preview`: Failure to include signatures will result in a 400 error. The verbiage will be of the form:
    - Function call`<Function Call>`in the`<index of contents array>`content block is missing a`thought_signature`. For example,*Function call`FC1`in the`1.`content block is missing a`thought_signature`.*

### Sequential function calling example

This section shows an example of multiple function calls where the user asks a complex question requiring multiple tasks.

Let's walk through a multiple-turn function calling example where the user asks a complex question requiring multiple tasks:`"Check flight status for AA100 and
book a taxi if delayed"`.

|----------|----------|---------------------------------------------------------------------------------------|------------------------------------|----------------------|
| **Turn** | **Step** | **User Request**                                                                      | **Model Response**                 | **FunctionResponse** |
| 1        | 1        | `request1="Check flight status for AA100 and book a taxi 2 hours before if delayed."` | `FC1 ("check_flight") + signature` | `FR1`                |
| 1        | 2        | `request2 `**=**` request1 `**+**` FC1 ("check_flight") + signature + FR1`            | `FC2("book_taxi") + signature`     | `FR2`                |
| 1        | 3        | `request3 `**=**` request2 `**+**` FC2 ("book_taxi") + signature + FR2`               | `text_output` <br /> `(no FCs)`    | `None`               |

The following code illustrates the sequence in the above table.

**Turn 1, Step 1 (User request)**

    {
      "contents": [
        {
          "role": "user",
          "parts": [
            {
              "text": "Check flight status for AA100 and book a taxi 2 hours before if delayed."
            }
          ]
        }
      ],
      "tools": [
        {
          "functionDeclarations": [
            {
              "name": "check_flight",
              "description": "Gets the current status of a flight",
              "parameters": {
                "type": "object",
                "properties": {
                  "flight": {
                    "type": "string",
                    "description": "The flight number to check"
                  }
                },
                "required": [
                  "flight"
                ]
              }
            },
            {
              "name": "book_taxi",
              "description": "Book a taxi",
              "parameters": {
                "type": "object",
                "properties": {
                  "time": {
                    "type": "string",
                    "description": "time to book the taxi"
                  }
                },
                "required": [
                  "time"
                ]
              }
            }
          ]
        }
      ]
    }

**Turn 1, Step 1 (Model response)**

    {
    "content": {
            "role": "model",
            "parts": [
              {
                "functionCall": {
                  "name": "check_flight",
                  "args": {
                    "flight": "AA100"
                  }
                },
                "thoughtSignature": "<Signature A>"
              }
            ]
      }
    }

**Turn 1, Step 2 (User response - Sending tool outputs)** Since this user turn only contains a`functionResponse`(no fresh text), we are still in Turn 1. We must preserve`<Signature_A>`.

    {
          "role": "user",
          "parts": [
            {
              "text": "Check flight status for AA100 and book a taxi 2 hours before if delayed."
            }
          ]
        },
        {
            "role": "model",
            "parts": [
              {
                "functionCall": {
                  "name": "check_flight",
                  "args": {
                    "flight": "AA100"
                  }
                },
                "thoughtSignature": "<Signature A>" //Required and Validated
              }
            ]
          },
          {
            "role": "user",
            "parts": [
              {
                "functionResponse": {
                  "name": "check_flight",
                  "response": {
                    "status": "delayed",
                    "departure_time": "12 PM"
                    }
                  }
                }
            ]
    }

**Turn 1, Step 2 (Model)**The model now decides to book a taxi based on the previous tool output.

    {
          "content": {
            "role": "model",
            "parts": [
              {
                "functionCall": {
                  "name": "book_taxi",
                  "args": {
                    "time": "10 AM"
                  }
                },
                "thoughtSignature": "<Signature B>"
              }
            ]
          }
    }

**Turn 1, Step 3 (User - Sending tool output)** To send the taxi booking confirmation, we must include signatures for**ALL** function calls in this loop (`<Signature A>`+`<Signature B>`).

    {
          "role": "user",
          "parts": [
            {
              "text": "Check flight status for AA100 and book a taxi 2 hours before if delayed."
            }
          ]
        },
        {
            "role": "model",
            "parts": [
              {
                "functionCall": {
                  "name": "check_flight",
                  "args": {
                    "flight": "AA100"
                  }
                },
                "thoughtSignature": "<Signature A>" //Required and Validated
              }
            ]
          },
          {
            "role": "user",
            "parts": [
              {
                "functionResponse": {
                  "name": "check_flight",
                  "response": {
                    "status": "delayed",
                    "departure_time": "12 PM"
                  }
                  }
                }
            ]
          },
          {
            "role": "model",
            "parts": [
              {
                "functionCall": {
                  "name": "book_taxi",
                  "args": {
                    "time": "10 AM"
                  }
                },
                "thoughtSignature": "<Signature B>" //Required and Validated
              }
            ]
          },
          {
            "role": "user",
            "parts": [
              {
                "functionResponse": {
                  "name": "book_taxi",
                  "response": {
                    "booking_status": "success"
                  }
                  }
                }
            ]
        }
    }

### Parallel function calling example

Let's walk through a parallel function calling example where the users asks`"Check weather in Paris and London"`to see where the model does validation.

| **Turn** | **Step** |                            **User Request**                            |            **Model Response**            | **FunctionResponse** |
|----------|----------|------------------------------------------------------------------------|------------------------------------------|----------------------|
| 1        | 1        | request1="Check the weather in Paris and London"                       | FC1 ("Paris") + signature FC2 ("London") | FR1                  |
| 1        | 2        | request 2**=** request1**+**FC1 ("Paris") + signature + FC2 ("London") | text_output (no FCs)                     | None                 |

The following code illustrates the sequence in the above table.

**Turn 1, Step 1 (User request)**

    {
      "contents": [
        {
          "role": "user",
          "parts": [
            {
              "text": "Check the weather in Paris and London."
            }
          ]
        }
      ],
      "tools": [
        {
          "functionDeclarations": [
            {
              "name": "get_current_temperature",
              "description": "Gets the current temperature for a given location.",
              "parameters": {
                "type": "object",
                "properties": {
                  "location": {
                    "type": "string",
                    "description": "The city name, e.g. San Francisco"
                  }
                },
                "required": [
                  "location"
                ]
              }
            }
          ]
        }
      ]
    }

**Turn 1, Step 1 (Model response)**

    {
      "content": {
        "parts": [
          {
            "functionCall": {
              "name": "get_current_temperature",
              "args": {
                "location": "Paris"
              }
            },
            "thoughtSignature": "<Signature_A>"// INCLUDED on First FC
          },
          {
            "functionCall": {
              "name": "get_current_temperature",
              "args": {
                "location": "London"
              }// NO signature on subsequent parallel FCs
            }
          }
        ]
      }
    }

**Turn 1, Step 2 (User response - Sending tool outputs)** We must preserve`<Signature_A>`on the first part exactly as received.

    [
      {
        "role": "user",
        "parts": [
          {
            "text": "Check the weather in Paris and London."
          }
        ]
      },
      {
        "role": "model",
        "parts": [
          {
            "functionCall": {
              "name": "get_current_temperature",
              "args": {
                "city": "Paris"
              }
            },
            "thought_signature": "<Signature_A>" // MUST BE INCLUDED
          },
          {
            "functionCall": {
              "name": "get_current_temperature",
              "args": {
                "city": "London"
              }
            }
          } // NO SIGNATURE FIELD
        ]
      },
      {
        "role": "user",
        "parts": [
          {
            "functionResponse": {
              "name": "get_current_temperature",
              "response": {
                "temp": "15C"
              }
            }
          },
          {
            "functionResponse": {
              "name": "get_current_temperature",
              "response": {
                "temp": "12C"
              }
            }
          }
        ]
      }
    ]

## Signatures in non`functionCall`parts

Gemini may also return`thought_signatures`in the final part of the response in non-function-call parts.

- **Behavior** : The final content part (`text, inlineData...`) returned by the model may contain a`thought_signature`.
- **Recommendation** : Returning these signatures is**recommended**to ensure the model maintains high-quality reasoning, especially for complex instruction following or simulated agentic workflows.
- **Validation** : The API does**not**strictly enforce validation. You won't receive a blocking error if you omit them, though performance may degrade.

### Text/In-context reasoning (No validation)

**Turn 1, Step 1 (Model response)**

    {
      "role": "model",
      "parts": [
        {
          "text": "I need to calculate the risk. Let me think step-by-step...",
          "thought_signature": "<Signature_C>" // OPTIONAL (Recommended)
        }
      ]
    }

**Turn 2, Step 1 (User)**

    [
      { "role": "user", "parts": [{ "text": "What is the risk?" }] },
      {
        "role": "model",
        "parts": [
          {
            "text": "I need to calculate the risk. Let me think step-by-step...",
            // If you omit <Signature_C> here, no error will occur.
          }
        ]
      },
      { "role": "user", "parts": [{ "text": "Summarize it." }] }
    ]

## Signatures for OpenAI compatibility

The following examples shows how to handle thought signatures for a chat completion API using[OpenAI compatibility](https://ai.google.dev/gemini-api/docs/openai).

### Sequential function calling example

This is an example of multiple function calling where the user asks a complex question requiring multiple tasks.

Let's walk through a multiple-turn function calling example where the user asks`Check flight status for AA100 and book a taxi if delayed`and you can see what happens when the user asks a complex question requiring multiple tasks.

|----------|----------|---------------------------------------------------------------------------------|-----------------------------------------------------|----------------------|
| **Turn** | **Step** | **User Request**                                                                | **Model Response**                                  | **FunctionResponse** |
| 1        | 1        | `request1="Check the weather in Paris and London"`                              | `FC1 ("Paris") + signature` <br /> `FC2 ("London")` | `FR1`                |
| 1        | 2        | `request 2 `**=**` request1 `**+**` FC1 ("Paris") + signature + FC2 ("London")` | `text_output` <br /> `(no FCs)`                     | `None`               |

The following code walks through the given sequence.

**Turn 1, Step 1 (User Request)**

    {
      "model": "google/gemini-3-pro-preview",
      "messages": [
        {
          "role": "user",
          "content": "Check flight status for AA100 and book a taxi 2 hours before if delayed."
        }
      ],
      "tools": [
        {
          "type": "function",
          "function": {
            "name": "check_flight",
            "description": "Gets the current status of a flight",
            "parameters": {
              "type": "object",
              "properties": {
                "flight": {
                  "type": "string",
                  "description": "The flight number to check."
                }
              },
              "required": [
                "flight"
              ]
            }
          }
        },
        {
          "type": "function",
          "function": {
            "name": "book_taxi",
            "description": "Book a taxi",
            "parameters": {
              "type": "object",
              "properties": {
                "time": {
                  "type": "string",
                  "description": "time to book the taxi"
                }
              },
              "required": [
                "time"
              ]
            }
          }
        }
      ]
    }

**Turn 1, Step 1 (Model Response)**

    {
          "role": "model",
            "tool_calls": [
              {
                "extra_content": {
                  "google": {
                    "thought_signature": "<Signature A>"
                  }
                },
                "function": {
                  "arguments": "{\"flight\":\"AA100\"}",
                  "name": "check_flight"
                },
                "id": "function-call-1",
                "type": "function"
              }
            ]
        }

**Turn 1, Step 2 (User Response - Sending Tool Outputs)**

Since this user turn only contains a`functionResponse`(no fresh text), we are still in Turn 1 and must preserve`<Signature_A>`.

    "messages": [
        {
          "role": "user",
          "content": "Check flight status for AA100 and book a taxi 2 hours before if delayed."
        },
        {
          "role": "model",
            "tool_calls": [
              {
                "extra_content": {
                  "google": {
                    "thought_signature": "<Signature A>" //Required and Validated
                  }
                },
                "function": {
                  "arguments": "{\"flight\":\"AA100\"}",
                  "name": "check_flight"
                },
                "id": "function-call-1",
                "type": "function"
              }
            ]
        },
        {
          "role": "tool",
          "name": "check_flight",
          "tool_call_id": "function-call-1",
          "content": "{\"status\":\"delayed\",\"departure_time\":\"12 PM\"}"
        }
      ]

**Turn 1, Step 2 (Model)**

The model now decides to book a taxi based on the previous tool output.

    {
    "role": "model",
    "tool_calls": [
    {
    "extra_content": {
    "google": {
    "thought_signature": "<Signature B>"
    }
                },
                "function": {
                  "arguments": "{\"time\":\"10 AM\"}",
                  "name": "book_taxi"
                },
                "id": "function-call-2",
                "type": "function"
              }
           ]
    }

**Turn 1, Step 3 (User - Sending Tool Output)**

To send the taxi booking confirmation, we must include signatures for ALL function calls in this loop (`<Signature A>`+`<Signature B>`).

    "messages": [
        {
          "role": "user",
          "content": "Check flight status for AA100 and book a taxi 2 hours before if delayed."
        },
        {
          "role": "model",
            "tool_calls": [
              {
                "extra_content": {
                  "google": {
                    "thought_signature": "<Signature A>" //Required and Validated
                  }
                },
                "function": {
                  "arguments": "{\"flight\":\"AA100\"}",
                  "name": "check_flight"
                },
                "id": "function-call-1d6a1a61-6f4f-4029-80ce-61586bd86da5",
                "type": "function"
              }
            ]
        },
        {
          "role": "tool",
          "name": "check_flight",
          "tool_call_id": "function-call-1d6a1a61-6f4f-4029-80ce-61586bd86da5",
          "content": "{\"status\":\"delayed\",\"departure_time\":\"12 PM\"}"
        },
        {
          "role": "model",
            "tool_calls": [
              {
                "extra_content": {
                  "google": {
                    "thought_signature": "<Signature B>" //Required and Validated
                  }
                },
                "function": {
                  "arguments": "{\"time\":\"10 AM\"}",
                  "name": "book_taxi"
                },
                "id": "function-call-65b325ba-9b40-4003-9535-8c7137b35634",
                "type": "function"
              }
            ]
        },
        {
          "role": "tool",
          "name": "book_taxi",
          "tool_call_id": "function-call-65b325ba-9b40-4003-9535-8c7137b35634",
          "content": "{\"booking_status\":\"success\"}"
        }
      ]

### Parallel function calling example

Let's walk through a parallel function calling example where the users asks`"Check weather in Paris and London"`and you can see where the model does validation.

|----------|----------|---------------------------------------------------------------------------------|-----------------------------------------------------|----------------------|
| **Turn** | **Step** | **User Request**                                                                | **Model Response**                                  | **FunctionResponse** |
| 1        | 1        | `request1="Check the weather in Paris and London"`                              | `FC1 ("Paris") + signature` <br /> `FC2 ("London")` | `FR1`                |
| 1        | 2        | `request 2 `**=**` request1 `**+**` FC1 ("Paris") + signature + FC2 ("London")` | `text_output` <br /> `(no FCs)`                     | `None`               |

Here's the code to walk through the given sequence.

**Turn 1, Step 1 (User Request)**

    {
      "contents": [
        {
          "role": "user",
          "parts": [
            {
              "text": "Check the weather in Paris and London."
            }
          ]
        }
      ],
      "tools": [
        {
          "functionDeclarations": [
            {
              "name": "get_current_temperature",
              "description": "Gets the current temperature for a given location.",
              "parameters": {
                "type": "object",
                "properties": {
                  "location": {
                    "type": "string",
                    "description": "The city name, e.g. San Francisco"
                  }
                },
                "required": [
                  "location"
                ]
              }
            }
          ]
        }
      ]
    }

**Turn 1, Step 1 (Model Response)**

    {
    "role": "assistant",
            "tool_calls": [
              {
                "extra_content": {
                  "google": {
                    "thought_signature": "<Signature A>" //Signature returned
                  }
                },
                "function": {
                  "arguments": "{\"location\":\"Paris\"}",
                  "name": "get_current_temperature"
                },
                "id": "function-call-f3b9ecb3-d55f-4076-98c8-b13e9d1c0e01",
                "type": "function"
              },
              {
                "function": {
                  "arguments": "{\"location\":\"London\"}",
                  "name": "get_current_temperature"
                },
                "id": "function-call-335673ad-913e-42d1-bbf5-387c8ab80f44",
                "type": "function" // No signature on Parallel FC
              }
            ]
    }

**Turn 1, Step 2 (User Response - Sending Tool Outputs)**

You must preserve`<Signature_A>`on the first part exactly as received.

    "messages": [
        {
          "role": "user",
          "content": "Check the weather in Paris and London."
        },
        {
          "role": "assistant",
            "tool_calls": [
              {
                "extra_content": {
                  "google": {
                    "thought_signature": "<Signature A>" //Required
                  }
                },
                "function": {
                  "arguments": "{\"location\":\"Paris\"}",
                  "name": "get_current_temperature"
                },
                "id": "function-call-f3b9ecb3-d55f-4076-98c8-b13e9d1c0e01",
                "type": "function"
              },
              {
                "function": { //No Signature
                  "arguments": "{\"location\":\"London\"}",
                  "name": "get_current_temperature"
                },
                "id": "function-call-335673ad-913e-42d1-bbf5-387c8ab80f44",
                "type": "function"
              }
            ]
        },
        {
          "role":"tool",
          "name": "get_current_temperature",
          "tool_call_id": "function-call-f3b9ecb3-d55f-4076-98c8-b13e9d1c0e01",
          "content": "{\"temp\":\"15C\"}"
        },
        {
          "role":"tool",
          "name": "get_current_temperature",
          "tool_call_id": "function-call-335673ad-913e-42d1-bbf5-387c8ab80f44",
          "content": "{\"temp\":\"12C\"}"
        }
      ]

## FAQs

1. **How do I transfer history from a different model to Gemini 3 with a function call part in the current turn and step? I need to provide function call parts that were not generated by the API and therefore don't have an associated thought signature?**

   While injecting custom function call blocks into the request is strongly discouraged, in cases where it can't be avoided, e.g. providing information to the model on function calls and responses that were executed deterministically by the client, or transferring a trace from a different model that does not include thought signatures, you can set the following dummy signatures of either`"context_engineering_is_the_way_to_go"`or`"skip_thought_signature_validator"`in the thought signature field to skip validation.
2. **I am sending back interleaved parallel function calls and responses and the API is returning a 400. Why?**

   When the API returns parallel function calls "FC1 + signature, FC2", the user response expected is "FC1+ signature, FC2, FR1, FR2". If you have them interleaved as "FC1 + signature, FR1, FC2, FR2" the API will return a 400 error.
3. **When streaming and the model is not returning a function call I can't find the thought signature**

   During a model response not containing a FC with a streaming request, the model may return the thought signature in a part with an empty text content part. It is advisable to parse the entire request until the`finish_reason`is returned by the model.

## Thought signatures for different models

Gemini 3 Pro and Flash, Gemini 3 Pro Image and Gemini 2.5 models each behave differently with thought signatures. For Gemini 3 Pro Image see the thinking process section of the[image generation](https://ai.google.dev/gemini-api/docs/image-generation#thinking-process)guide.

Gemini 3 models and Gemini 2.5 models behave differently with thought signatures in function calls:

- If there are function calls in a response,
  - Gemini 3 will always have the signature on the first function call part. It is**mandatory**to return that part.
  - Gemini 2.5 will have the signature in the first part (regardless of type). It is**optional**to return that part.
- If there are no function calls in a response,
  - Gemini 3 will have the signature on the last part if the model generates a thought.
  - Gemini 2.5 won't have a signature in any part.

For Gemini 2.5 models thought signature behavior, refer to the[Thinking](https://ai.google.dev/gemini-api/docs/thinking#signatures)page.

You can configure Gemini models to generate responses that adhere to a provided JSON
Schema. This ensures predictable, type-safe results and simplifies extracting
structured data from unstructured text.

Using structured outputs is ideal for:

- **Data extraction:** Pull specific information like names and dates from text.
- **Structured classification:** Classify text into predefined categories.
- **Agentic workflows:** Generate structured inputs for tools or APIs.

In addition to supporting JSON Schema in the REST API, the Google GenAI SDKs
make it easy to define schemas using
[Pydantic](https://docs.pydantic.dev/latest/) (Python) and
[Zod](https://zod.dev/) (JavaScript).

<button value="recipe" default="">Recipe Extractor</button> <button value="feedback">Content Moderation</button> <button value="recursive">Recursive Structures</button>

This example demonstrates how to extract structured data from text using basic JSON Schema types like `object`, `array`, `string`, and `integer`.

### Python

    from google import genai
    from pydantic import BaseModel, Field
    from typing import List, Optional

    class Ingredient(BaseModel):
        name: str = Field(description="Name of the ingredient.")
        quantity: str = Field(description="Quantity of the ingredient, including units.")

    class Recipe(BaseModel):
        recipe_name: str = Field(description="The name of the recipe.")
        prep_time_minutes: Optional[int] = Field(description="Optional time in minutes to prepare the recipe.")
        ingredients: List[Ingredient]
        instructions: List[str]

    client = genai.Client()

    prompt = """
    Please extract the recipe from the following text.
    The user wants to make delicious chocolate chip cookies.
    They need 2 and 1/4 cups of all-purpose flour, 1 teaspoon of baking soda,
    1 teaspoon of salt, 1 cup of unsalted butter (softened), 3/4 cup of granulated sugar,
    3/4 cup of packed brown sugar, 1 teaspoon of vanilla extract, and 2 large eggs.
    For the best part, they'll need 2 cups of semisweet chocolate chips.
    First, preheat the oven to 375°F (190°C). Then, in a small bowl, whisk together the flour,
    baking soda, and salt. In a large bowl, cream together the butter, granulated sugar, and brown sugar
    until light and fluffy. Beat in the vanilla and eggs, one at a time. Gradually beat in the dry
    ingredients until just combined. Finally, stir in the chocolate chips. Drop by rounded tablespoons
    onto ungreased baking sheets and bake for 9 to 11 minutes.
    """

    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_json_schema": Recipe.model_json_schema(),
        },
    )

    recipe = Recipe.model_validate_json(response.text)
    print(recipe)

### JavaScript

    import { GoogleGenAI } from "@google/genai";
    import { z } from "zod";
    import { zodToJsonSchema } from "zod-to-json-schema";

    const ingredientSchema = z.object({
      name: z.string().describe("Name of the ingredient."),
      quantity: z.string().describe("Quantity of the ingredient, including units."),
    });

    const recipeSchema = z.object({
      recipe_name: z.string().describe("The name of the recipe."),
      prep_time_minutes: z.number().optional().describe("Optional time in minutes to prepare the recipe."),
      ingredients: z.array(ingredientSchema),
      instructions: z.array(z.string()),
    });

    const ai = new GoogleGenAI({});

    const prompt = `
    Please extract the recipe from the following text.
    The user wants to make delicious chocolate chip cookies.
    They need 2 and 1/4 cups of all-purpose flour, 1 teaspoon of baking soda,
    1 teaspoon of salt, 1 cup of unsalted butter (softened), 3/4 cup of granulated sugar,
    3/4 cup of packed brown sugar, 1 teaspoon of vanilla extract, and 2 large eggs.
    For the best part, they'll need 2 cups of semisweet chocolate chips.
    First, preheat the oven to 375°F (190°C). Then, in a small bowl, whisk together the flour,
    baking soda, and salt. In a large bowl, cream together the butter, granulated sugar, and brown sugar
    until light and fluffy. Beat in the vanilla and eggs, one at a time. Gradually beat in the dry
    ingredients until just combined. Finally, stir in the chocolate chips. Drop by rounded tablespoons
    onto ungreased baking sheets and bake for 9 to 11 minutes.
    `;

    const response = await ai.models.generateContent({
      model: "gemini-3-flash-preview",
      contents: prompt,
      config: {
        responseMimeType: "application/json",
        responseJsonSchema: zodToJsonSchema(recipeSchema),
      },
    });

    const recipe = recipeSchema.parse(JSON.parse(response.text));
    console.log(recipe);

### Go

    package main

    import (
        "context"
        "fmt"
        "log"

        "google.golang.org/genai"
    )

    func main() {
        ctx := context.Background()
        client, err := genai.NewClient(ctx, nil)
        if err != nil {
            log.Fatal(err)
        }

        prompt := `
      Please extract the recipe from the following text.
      The user wants to make delicious chocolate chip cookies.
      They need 2 and 1/4 cups of all-purpose flour, 1 teaspoon of baking soda,
      1 teaspoon of salt, 1 cup of unsalted butter (softened), 3/4 cup of granulated sugar,
      3/4 cup of packed brown sugar, 1 teaspoon of vanilla extract, and 2 large eggs.
      For the best part, they'll need 2 cups of semisweet chocolate chips.
      First, preheat the oven to 375°F (190°C). Then, in a small bowl, whisk together the flour,
      baking soda, and salt. In a large bowl, cream together the butter, granulated sugar, and brown sugar
      until light and fluffy. Beat in the vanilla and eggs, one at a time. Gradually beat in the dry
      ingredients until just combined. Finally, stir in the chocolate chips. Drop by rounded tablespoons
      onto ungreased baking sheets and bake for 9 to 11 minutes.
      `
        config := &genai.GenerateContentConfig{
            ResponseMIMEType: "application/json",
            ResponseJsonSchema: map[string]any{
                "type": "object",
                "properties": map[string]any{
                    "recipe_name": map[string]any{
                        "type":        "string",
                        "description": "The name of the recipe.",
                    },
                    "prep_time_minutes": map[string]any{
                        "type":        "integer",
                        "description": "Optional time in minutes to prepare the recipe.",
                    },
                    "ingredients": map[string]any{
                        "type": "array",
                        "items": map[string]any{
                            "type": "object",
                            "properties": map[string]any{
                                "name": map[string]any{
                                    "type":        "string",
                                    "description": "Name of the ingredient.",
                                },
                                "quantity": map[string]any{
                                    "type":        "string",
                                    "description": "Quantity of the ingredient, including units.",
                                },
                            },
                            "required": []string{"name", "quantity"},
                        },
                    },
                    "instructions": map[string]any{
                        "type":  "array",
                        "items": map[string]any{"type": "string"},
                    },
                },
                "required": []string{"recipe_name", "ingredients", "instructions"},
            },
        }

        result, err := client.Models.GenerateContent(
            ctx,
            "gemini-3-flash-preview",
            genai.Text(prompt),
            config,
        )
        if err != nil {
            log.Fatal(err)
        }
        fmt.Println(result.Text())
    }

### REST

    curl "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent" \
        -H "x-goog-api-key: $GEMINI_API_KEY" \
        -H 'Content-Type: application/json' \
        -X POST \
        -d '{
          "contents": [{
            "parts":[
              { "text": "Please extract the recipe from the following text.\nThe user wants to make delicious chocolate chip cookies.\nThey need 2 and 1/4 cups of all-purpose flour, 1 teaspoon of baking soda,\n1 teaspoon of salt, 1 cup of unsalted butter (softened), 3/4 cup of granulated sugar,\n3/4 cup of packed brown sugar, 1 teaspoon of vanilla extract, and 2 large eggs.\nFor the best part, they will need 2 cups of semisweet chocolate chips.\nFirst, preheat the oven to 375°F (190°C). Then, in a small bowl, whisk together the flour,\nbaking soda, and salt. In a large bowl, cream together the butter, granulated sugar, and brown sugar\nuntil light and fluffy. Beat in the vanilla and eggs, one at a time. Gradually beat in the dry\ningredients until just combined. Finally, stir in the chocolate chips. Drop by rounded tablespoons\nonto ungreased baking sheets and bake for 9 to 11 minutes." }
            ]
          }],
          "generationConfig": {
            "responseMimeType": "application/json",
            "responseJsonSchema": {
              "type": "object",
              "properties": {
                "recipe_name": {
                  "type": "string",
                  "description": "The name of the recipe."
                },
                "prep_time_minutes": {
                    "type": "integer",
                    "description": "Optional time in minutes to prepare the recipe."
                },
                "ingredients": {
                  "type": "array",
                  "items": {
                    "type": "object",
                    "properties": {
                      "name": { "type": "string", "description": "Name of the ingredient."},
                      "quantity": { "type": "string", "description": "Quantity of the ingredient, including units."}
                    },
                    "required": ["name", "quantity"]
                  }
                },
                "instructions": {
                  "type": "array",
                  "items": { "type": "string" }
                }
              },
              "required": ["recipe_name", "ingredients", "instructions"]
            }
          }
        }'

**Example Response:**

    {
      "recipe_name": "Delicious Chocolate Chip Cookies",
      "ingredients": [
        {
          "name": "all-purpose flour",
          "quantity": "2 and 1/4 cups"
        },
        {
          "name": "baking soda",
          "quantity": "1 teaspoon"
        },
        {
          "name": "salt",
          "quantity": "1 teaspoon"
        },
        {
          "name": "unsalted butter (softened)",
          "quantity": "1 cup"
        },
        {
          "name": "granulated sugar",
          "quantity": "3/4 cup"
        },
        {
          "name": "packed brown sugar",
          "quantity": "3/4 cup"
        },
        {
          "name": "vanilla extract",
          "quantity": "1 teaspoon"
        },
        {
          "name": "large eggs",
          "quantity": "2"
        },
        {
          "name": "semisweet chocolate chips",
          "quantity": "2 cups"
        }
      ],
      "instructions": [
        "Preheat the oven to 375°F (190°C).",
        "In a small bowl, whisk together the flour, baking soda, and salt.",
        "In a large bowl, cream together the butter, granulated sugar, and brown sugar until light and fluffy.",
        "Beat in the vanilla and eggs, one at a time.",
        "Gradually beat in the dry ingredients until just combined.",
        "Stir in the chocolate chips.",
        "Drop by rounded tablespoons onto ungreased baking sheets and bake for 9 to 11 minutes."
      ]
    }

## Streaming

You can stream structured outputs, which allows you to start processing the response as it's being generated, without having to wait for the entire output to be complete. This can improve the perceived performance of your application.

The streamed chunks will be valid partial JSON strings, which can be concatenated to form the final, complete JSON object.

### Python

    from google import genai
    from pydantic import BaseModel, Field
    from typing import Literal

    class Feedback(BaseModel):
        sentiment: Literal["positive", "neutral", "negative"]
        summary: str

    client = genai.Client()
    prompt = "The new UI is incredibly intuitive and visually appealing. Great job. Add a very long summary to test streaming!"

    response_stream = client.models.generate_content_stream(
        model="gemini-3-flash-preview",
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_json_schema": Feedback.model_json_schema(),
        },
    )

    for chunk in response_stream:
        print(chunk.candidates[0].content.parts[0].text)

### JavaScript

    import { GoogleGenAI } from "@google/genai";
    import { z } from "zod";
    import { zodToJsonSchema } from "zod-to-json-schema";

    const ai = new GoogleGenAI({});
    const prompt = "The new UI is incredibly intuitive and visually appealing. Great job! Add a very long summary to test streaming!";

    const feedbackSchema = z.object({
      sentiment: z.enum(["positive", "neutral", "negative"]),
      summary: z.string(),
    });

    const stream = await ai.models.generateContentStream({
      model: "gemini-3-flash-preview",
      contents: prompt,
      config: {
        responseMimeType: "application/json",
        responseJsonSchema: zodToJsonSchema(feedbackSchema),
      },
    });

    for await (const chunk of stream) {
      console.log(chunk.candidates[0].content.parts[0].text)
    }

## Structured outputs with tools

| **Preview:** This is a feature available only for the Gemini 3 series models, `gemini-3-pro-preview` and `gemini-3-flash-preview`.

Gemini 3 lets you combine Structured Outputs with built-in tools, including
[Grounding with Google Search](https://ai.google.dev/gemini-api/docs/google-search),
[URL Context](https://ai.google.dev/gemini-api/docs/url-context),
[Code Execution](https://ai.google.dev/gemini-api/docs/code-execution),
[File Search](https://ai.google.dev/gemini-api/docs/file-search#structured-output), and
[Function Calling](https://ai.google.dev/gemini-api/docs/function-calling).

### Python

    from google import genai
    from pydantic import BaseModel, Field
    from typing import List

    class MatchResult(BaseModel):
        winner: str = Field(description="The name of the winner.")
        final_match_score: str = Field(description="The final match score.")
        scorers: List[str] = Field(description="The name of the scorer.")

    client = genai.Client()

    response = client.models.generate_content(
        model="gemini-3-pro-preview",
        contents="Search for all details for the latest Euro.",
        config={
            "tools": [
                {"google_search": {}},
                {"url_context": {}}
            ],
            "response_mime_type": "application/json",
            "response_json_schema": MatchResult.model_json_schema(),
        },
    )

    result = MatchResult.model_validate_json(response.text)
    print(result)

### JavaScript

    import { GoogleGenAI } from "@google/genai";
    import { z } from "zod";
    import { zodToJsonSchema } from "zod-to-json-schema";

    const ai = new GoogleGenAI({});

    const matchSchema = z.object({
      winner: z.string().describe("The name of the winner."),
      final_match_score: z.string().describe("The final score."),
      scorers: z.array(z.string()).describe("The name of the scorer.")
    });

    async function run() {
      const response = await ai.models.generateContent({
        model: "gemini-3-pro-preview",
        contents: "Search for all details for the latest Euro.",
        config: {
          tools: [
            { googleSearch: {} },
            { urlContext: {} }
          ],
          responseMimeType: "application/json",
          responseJsonSchema: zodToJsonSchema(matchSchema),
        },
      });

      const match = matchSchema.parse(JSON.parse(response.text));
      console.log(match);
    }

    run();

### REST

    curl "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-pro-preview:generateContent" \
      -H "x-goog-api-key: $GEMINI_API_KEY" \
      -H 'Content-Type: application/json' \
      -X POST \
      -d '{
        "contents": [{
          "parts": [{"text": "Search for all details for the latest Euro."}]
        }],
        "tools": [
          {"googleSearch": {}},
          {"urlContext": {}}
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseJsonSchema": {
                "type": "object",
                "properties": {
                    "winner": {"type": "string", "description": "The name of the winner."},
                    "final_match_score": {"type": "string", "description": "The final score."},
                    "scorers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "The name of the scorer."
                    }
                },
                "required": ["winner", "final_match_score", "scorers"]
            }
        }
      }'

## JSON schema support

To generate a JSON object, set the `response_mime_type` in the generation configuration to `application/json` and provide a `response_json_schema`. The schema must be a valid [JSON Schema](https://json-schema.org/) that describes the desired output format.

The model will then generate a response that is a syntactically valid JSON string matching the provided schema. When using structured outputs, the model will produce outputs in the same order as the keys in the schema.

Gemini's structured output mode supports a subset of the [JSON Schema](https://json-schema.org) specification.

The following values of `type` are supported:

- **`string`**: For text.
- **`number`**: For floating-point numbers.
- **`integer`**: For whole numbers.
- **`boolean`**: For true/false values.
- **`object`**: For structured data with key-value pairs.
- **`array`**: For lists of items.
- **`null`** : To allow a property to be null, include `"null"` in the type array (e.g., `{"type": ["string", "null"]}`).

These descriptive properties help guide the model:

- **`title`**: A short description of a property.
- **`description`**: A longer and more detailed description of a property.

### Type-specific properties

**For `object` values:**

- **`properties`**: An object where each key is a property name and each value is a schema for that property.
- **`required`**: An array of strings, listing which properties are mandatory.
- **`additionalProperties`** : Controls whether properties not listed in `properties` are allowed. Can be a boolean or a schema.

**For `string` values:**

- **`enum`**: Lists a specific set of possible strings for classification tasks.
- **`format`** : Specifies a syntax for the string, such as `date-time`, `date`, `time`.

**For `number` and `integer` values:**

- **`enum`**: Lists a specific set of possible numeric values.
- **`minimum`**: The minimum inclusive value.
- **`maximum`**: The maximum inclusive value.

**For `array` values:**

- **`items`**: Defines the schema for all items in the array.
- **`prefixItems`**: Defines a list of schemas for the first N items, allowing for tuple-like structures.
- **`minItems`**: The minimum number of items in the array.
- **`maxItems`**: The maximum number of items in the array.

## Model support

The following models support structured output:

| Model | Structured Outputs |
|---|---|
| Gemini 3 Pro Preview | ✔️ |
| Gemini 3 Flash Preview | ✔️ |
| Gemini 2.5 Pro | ✔️ |
| Gemini 2.5 Flash | ✔️ |
| Gemini 2.5 Flash-Lite | ✔️ |
| Gemini 2.0 Flash | ✔️\* |
| Gemini 2.0 Flash-Lite | ✔️\* |

*\* Note that Gemini 2.0 requires an explicit `propertyOrdering` list within the JSON input to define the preferred structure. You can find an example in this [cookbook](https://github.com/google-gemini/cookbook/blob/main/examples/Pdf_structured_outputs_on_invoices_and_forms.ipynb).*

## Structured outputs vs. function calling

Both structured outputs and function calling use JSON schemas, but they serve different purposes:

| Feature | Primary Use Case |
|---|---|
| **Structured Outputs** | **Formatting the final response to the user.** Use this when you want the model's *answer* to be in a specific format (e.g., extracting data from a document to save to a database). |
| **Function Calling** | **Taking action during the conversation.** Use this when the model needs to *ask you* to perform a task (e.g., "get current weather") before it can provide a final answer. |

## Best practices

- **Clear descriptions:** Use the `description` field in your schema to provide clear instructions to the model about what each property represents. This is crucial for guiding the model's output.
- **Strong typing:** Use specific types (`integer`, `string`, `enum`) whenever possible. If a parameter has a limited set of valid values, use an `enum`.
- **Prompt engineering:** Clearly state in your prompt what you want the model to do. For example, "Extract the following information from the text..." or "Classify this feedback according to the provided schema...".
- **Validation:** While structured output guarantees syntactically correct JSON, it does not guarantee the values are semantically correct. Always validate the final output in your application code before using it.
- **Error handling:** Implement robust error handling in your application to gracefully manage cases where the model's output, while schema-compliant, may not meet your business logic requirements.

## Limitations

- **Schema subset:** Not all features of the JSON Schema specification are supported. The model ignores unsupported properties.
- **Schema complexity:** The API may reject very large or deeply nested schemas. If you encounter errors, try simplifying your schema by shortening property names, reducing nesting, or limiting the number of constraints.


Function calling lets you connect models to external tools and APIs.
Instead of generating text responses, the model determines when to call specific
functions and provides the necessary parameters to execute real-world actions.
This allows the model to act as a bridge between natural language and real-world
actions and data. Function calling has 3 primary use cases:

- **Augment Knowledge:** Access information from external sources like databases, APIs, and knowledge bases.
- **Extend Capabilities:** Use external tools to perform computations and extend the limitations of the model, such as using a calculator or creating charts.
- **Take Actions:** Interact with external systems using APIs, such as scheduling appointments, creating invoices, sending emails, or controlling smart home devices.

<button value="weather">Get Weather</button> <button value="meeting" default="">Schedule Meeting</button> <button value="chart">Create Chart</button>

### Python

    from google import genai
    from google.genai import types

    # Define the function declaration for the model
    schedule_meeting_function = {
        "name": "schedule_meeting",
        "description": "Schedules a meeting with specified attendees at a given time and date.",
        "parameters": {
            "type": "object",
            "properties": {
                "attendees": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of people attending the meeting.",
                },
                "date": {
                    "type": "string",
                    "description": "Date of the meeting (e.g., '2024-07-29')",
                },
                "time": {
                    "type": "string",
                    "description": "Time of the meeting (e.g., '15:00')",
                },
                "topic": {
                    "type": "string",
                    "description": "The subject or topic of the meeting.",
                },
            },
            "required": ["attendees", "date", "time", "topic"],
        },
    }

    # Configure the client and tools
    client = genai.Client()
    tools = types.Tool(function_declarations=[schedule_meeting_function])
    config = types.GenerateContentConfig(tools=[tools])

    # Send request with function declarations
    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents="Schedule a meeting with Bob and Alice for 03/14/2025 at 10:00 AM about the Q3 planning.",
        config=config,
    )

    # Check for a function call
    if response.candidates[0].content.parts[0].function_call:
        function_call = response.candidates[0].content.parts[0].function_call
        print(f"Function to call: {function_call.name}")
        print(f"Arguments: {function_call.args}")
        #  In a real app, you would call your function here:
        #  result = schedule_meeting(**function_call.args)
    else:
        print("No function call found in the response.")
        print(response.text)

### JavaScript

    import { GoogleGenAI, Type } from '@google/genai';

    // Configure the client
    const ai = new GoogleGenAI({});

    // Define the function declaration for the model
    const scheduleMeetingFunctionDeclaration = {
      name: 'schedule_meeting',
      description: 'Schedules a meeting with specified attendees at a given time and date.',
      parameters: {
        type: Type.OBJECT,
        properties: {
          attendees: {
            type: Type.ARRAY,
            items: { type: Type.STRING },
            description: 'List of people attending the meeting.',
          },
          date: {
            type: Type.STRING,
            description: 'Date of the meeting (e.g., "2024-07-29")',
          },
          time: {
            type: Type.STRING,
            description: 'Time of the meeting (e.g., "15:00")',
          },
          topic: {
            type: Type.STRING,
            description: 'The subject or topic of the meeting.',
          },
        },
        required: ['attendees', 'date', 'time', 'topic'],
      },
    };

    // Send request with function declarations
    const response = await ai.models.generateContent({
      model: 'gemini-3-flash-preview',
      contents: 'Schedule a meeting with Bob and Alice for 03/27/2025 at 10:00 AM about the Q3 planning.',
      config: {
        tools: [{
          functionDeclarations: [scheduleMeetingFunctionDeclaration]
        }],
      },
    });

    // Check for function calls in the response
    if (response.functionCalls && response.functionCalls.length > 0) {
      const functionCall = response.functionCalls[0]; // Assuming one function call
      console.log(`Function to call: ${functionCall.name}`);
      console.log(`Arguments: ${JSON.stringify(functionCall.args)}`);
      // In a real app, you would call your actual function here:
      // const result = await scheduleMeeting(functionCall.args);
    } else {
      console.log("No function call found in the response.");
      console.log(response.text);
    }

### REST

    curl "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent" \
      -H "x-goog-api-key: $GEMINI_API_KEY" \
      -H 'Content-Type: application/json' \
      -X POST \
      -d '{
        "contents": [
          {
            "role": "user",
            "parts": [
              {
                "text": "Schedule a meeting with Bob and Alice for 03/27/2025 at 10:00 AM about the Q3 planning."
              }
            ]
          }
        ],
        "tools": [
          {
            "functionDeclarations": [
              {
                "name": "schedule_meeting",
                "description": "Schedules a meeting with specified attendees at a given time and date.",
                "parameters": {
                  "type": "object",
                  "properties": {
                    "attendees": {
                      "type": "array",
                      "items": {"type": "string"},
                      "description": "List of people attending the meeting."
                    },
                    "date": {
                      "type": "string",
                      "description": "Date of the meeting (e.g., '2024-07-29')"
                    },
                    "time": {
                      "type": "string",
                      "description": "Time of the meeting (e.g., '15:00')"
                    },
                    "topic": {
                      "type": "string",
                      "description": "The subject or topic of the meeting."
                    }
                  },
                  "required": ["attendees", "date", "time", "topic"]
                }
              }
            ]
          }
        ]
      }'

## How function calling works

![function calling
overview](https://ai.google.dev/static/gemini-api/docs/images/function-calling-overview.png)

Function calling involves a structured interaction between your application, the
model, and external functions. Here's a breakdown of the process:

1. **Define Function Declaration:** Define the function declaration in your application code. Function Declarations describe the function's name, parameters, and purpose to the model.
2. **Call LLM with function declarations:** Send user prompt along with the function declaration(s) to the model. It analyzes the request and determines if a function call would be helpful. If so, it responds with a structured JSON object.
3. **Execute Function Code (Your Responsibility):** The Model *does not* execute the function itself. It's your application's responsibility to process the response and check for Function Call, if
   - **Yes**: Extract the name and args of the function and execute the corresponding function in your application.
   - **No:** The model has provided a direct text response to the prompt (this flow is less emphasized in the example but is a possible outcome).
4. **Create User friendly response:** If a function was executed, capture the result and send it back to the model in a subsequent turn of the conversation. It will use the result to generate a final, user-friendly response that incorporates the information from the function call.

This process can be repeated over multiple turns, allowing for complex
interactions and workflows. The model also supports calling multiple functions
in a single turn ([parallel function
calling](https://ai.google.dev/gemini-api/docs/function-calling#parallel_function_calling)) and in
sequence ([compositional function
calling](https://ai.google.dev/gemini-api/docs/function-calling#compositional_function_calling)).

### Step 1: Define a function declaration

Define a function and its declaration within your application code that allows
users to set light values and make an API request. This function could call
external services or APIs.

### Python

    # Define a function that the model can call to control smart lights
    set_light_values_declaration = {
        "name": "set_light_values",
        "description": "Sets the brightness and color temperature of a light.",
        "parameters": {
            "type": "object",
            "properties": {
                "brightness": {
                    "type": "integer",
                    "description": "Light level from 0 to 100. Zero is off and 100 is full brightness",
                },
                "color_temp": {
                    "type": "string",
                    "enum": ["daylight", "cool", "warm"],
                    "description": "Color temperature of the light fixture, which can be `daylight`, `cool` or `warm`.",
                },
            },
            "required": ["brightness", "color_temp"],
        },
    }

    # This is the actual function that would be called based on the model's suggestion
    def set_light_values(brightness: int, color_temp: str) -> dict[str, int | str]:
        """Set the brightness and color temperature of a room light. (mock API).

        Args:
            brightness: Light level from 0 to 100. Zero is off and 100 is full brightness
            color_temp: Color temperature of the light fixture, which can be `daylight`, `cool` or `warm`.

        Returns:
            A dictionary containing the set brightness and color temperature.
        """
        return {"brightness": brightness, "colorTemperature": color_temp}

### JavaScript

    import { Type } from '@google/genai';

    // Define a function that the model can call to control smart lights
    const setLightValuesFunctionDeclaration = {
      name: 'set_light_values',
      description: 'Sets the brightness and color temperature of a light.',
      parameters: {
        type: Type.OBJECT,
        properties: {
          brightness: {
            type: Type.NUMBER,
            description: 'Light level from 0 to 100. Zero is off and 100 is full brightness',
          },
          color_temp: {
            type: Type.STRING,
            enum: ['daylight', 'cool', 'warm'],
            description: 'Color temperature of the light fixture, which can be `daylight`, `cool` or `warm`.',
          },
        },
        required: ['brightness', 'color_temp'],
      },
    };

    /**

    *   Set the brightness and color temperature of a room light. (mock API)
    *   @param {number} brightness - Light level from 0 to 100. Zero is off and 100 is full brightness
    *   @param {string} color_temp - Color temperature of the light fixture, which can be `daylight`, `cool` or `warm`.
    *   @return {Object} A dictionary containing the set brightness and color temperature.
    */
    function setLightValues(brightness, color_temp) {
      return {
        brightness: brightness,
        colorTemperature: color_temp
      };
    }

### Step 2: Call the model with function declarations

Once you have defined your function declarations, you can prompt the model to
use them. It analyzes the prompt and function declarations and decides whether
to respond directly or to call a function. If a function is called, the response
object will contain a function call suggestion.

### Python

    from google.genai import types

    # Configure the client and tools
    client = genai.Client()
    tools = types.Tool(function_declarations=[set_light_values_declaration])
    config = types.GenerateContentConfig(tools=[tools])

    # Define user prompt
    contents = [
        types.Content(
            role="user", parts=[types.Part(text="Turn the lights down to a romantic level")]
        )
    ]

    # Send request with function declarations
    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=contents,
        config=config,
    )

    print(response.candidates[0].content.parts[0].function_call)

### JavaScript

    import { GoogleGenAI } from '@google/genai';

    // Generation config with function declaration
    const config = {
      tools: [{
        functionDeclarations: [setLightValuesFunctionDeclaration]
      }]
    };

    // Configure the client
    const ai = new GoogleGenAI({});

    // Define user prompt
    const contents = [
      {
        role: 'user',
        parts: [{ text: 'Turn the lights down to a romantic level' }]
      }
    ];

    // Send request with function declarations
    const response = await ai.models.generateContent({
      model: 'gemini-3-flash-preview',
      contents: contents,
      config: config
    });

    console.log(response.functionCalls[0]);

The model then returns a `functionCall` object in an OpenAPI compatible
schema specifying how to call one or more of the declared functions in order to
respond to the user's question.

### Python

    id=None args={'color_temp': 'warm', 'brightness': 25} name='set_light_values'

### JavaScript

    {
      name: 'set_light_values',
      args: { brightness: 25, color_temp: 'warm' }
    }

### Step 3: Execute set_light_values function code

Extract the function call details from the model's response, parse the arguments
, and execute the `set_light_values` function.

### Python

    # Extract tool call details, it may not be in the first part.
    tool_call = response.candidates[0].content.parts[0].function_call

    if tool_call.name == "set_light_values":
        result = set_light_values(**tool_call.args)
        print(f"Function execution result: {result}")

### JavaScript

    // Extract tool call details
    const tool_call = response.functionCalls[0]

    let result;
    if (tool_call.name === 'set_light_values') {
      result = setLightValues(tool_call.args.brightness, tool_call.args.color_temp);
      console.log(`Function execution result: ${JSON.stringify(result)}`);
    }

### Step 4: Create user friendly response with function result and call the model again

Finally, send the result of the function execution back to the model so it can
incorporate this information into its final response to the user.

### Python

    from google import genai
    from google.genai import types

    # Create a function response part
    function_response_part = types.Part.from_function_response(
        name=tool_call.name,
        response={"result": result},
    )

    # Append function call and result of the function execution to contents
    contents.append(response.candidates[0].content) # Append the content from the model's response.
    contents.append(types.Content(role="user", parts=[function_response_part])) # Append the function response

    client = genai.Client()
    final_response = client.models.generate_content(
        model="gemini-3-flash-preview",
        config=config,
        contents=contents,
    )

    print(final_response.text)

### JavaScript

    // Create a function response part
    const function_response_part = {
      name: tool_call.name,
      response: { result }
    }

    // Append function call and result of the function execution to contents
    contents.push(response.candidates[0].content);
    contents.push({ role: 'user', parts: [{ functionResponse: function_response_part }] });

    // Get the final response from the model
    const final_response = await ai.models.generateContent({
      model: 'gemini-3-flash-preview',
      contents: contents,
      config: config
    });

    console.log(final_response.text);

This completes the function calling flow. The model successfully used the
`set_light_values` function to perform the request action of the user.

## Function declarations

When you implement function calling in a prompt, you create a `tools` object,
which contains one or more `function declarations`. You define functions using
JSON, specifically with a [select subset](https://ai.google.dev/api/caching#Schema)
of the [OpenAPI schema](https://spec.openapis.org/oas/v3.0.3#schemaw) format. A
single function declaration can include the following parameters:

- `name` (string): A unique name for the function (`get_weather_forecast`, `send_email`). Use descriptive names without spaces or special characters (use underscores or camelCase).
- `description` (string): A clear and detailed explanation of the function's purpose and capabilities. This is crucial for the model to understand when to use the function. Be specific and provide examples if helpful ("Finds theaters based on location and optionally movie title which is currently playing in theaters.").
- `parameters` (object): Defines the input parameters the function expects.
  - `type` (string): Specifies the overall data type, such as `object`.
  - `properties` (object): Lists individual parameters, each with:
    - `type` (string): The data type of the parameter, such as `string`, `integer`, `boolean, array`.
    - `description` (string): A description of the parameter's purpose and format. Provide examples and constraints ("The city and state, e.g., 'San Francisco, CA' or a zip code e.g., '95616'.").
    - `enum` (array, optional): If the parameter values are from a fixed set, use "enum" to list the allowed values instead of just describing them in the description. This improves accuracy ("enum": \["daylight", "cool", "warm"\]).
  - `required` (array): An array of strings listing the parameter names that are mandatory for the function to operate.

You can also construct `FunctionDeclarations` from Python functions directly using
`types.FunctionDeclaration.from_callable(client=client, callable=your_function)`.

## Function calling with thinking models

Gemini 3 and 2.5 series models use an internal ["thinking"](https://ai.google.dev/gemini-api/docs/thinking) process to reason through requests. This
significantly improves function calling performance,
allowing the model to better determine when to call a function and which
parameters to use. Because the Gemini API is stateless, models use
[thought signatures](https://ai.google.dev/gemini-api/docs/thought-signatures) to maintain context
across multi-turn conversations.

This section covers advanced management of thought signatures and is only
necessary if you're manually constructing API requests (e.g., via REST) or
manipulating conversation history.

**If you're using the [Google GenAI SDKs](https://ai.google.dev/gemini-api/docs/libraries) (our
official libraries), you don't need to manage this process** . The SDKs
automatically handle the necessary steps, as shown in the earlier
[example](https://ai.google.dev/gemini-api/docs/function-calling#step-4).

### Managing conversation history manually

If you modify the conversation history manually, instead of sending the
[complete previous response](https://ai.google.dev/gemini-api/docs/function-calling#step-4) you
must correctly handle the `thought_signature` included in the model's turn.

Follow these rules to ensure the model's context is preserved:

- Always send the `thought_signature` back to the model inside its original [`Part`](https://ai.google.dev/api#request-body-structure).
- Don't merge a `Part` containing a signature with one that does not. This breaks the positional context of the thought.
- Don't combine two `Parts` that both contain signatures, as the signature strings cannot be merged.

#### Gemini 3 thought signatures

In Gemini 3, any [`Part`](https://ai.google.dev/api#request-body-structure) of a model response
may contain a thought signature.
While we generally recommend returning signatures from all `Part` types,
passing back thought signatures is mandatory for function calling. Unless you
are manipulating conversation history manually, the Google GenAI SDK will
handle thought signatures automatically.

If you are manipulating conversation history manually, refer to the
[Thoughts Signatures](https://ai.google.dev/gemini-api/docs/thought-signatures) page for complete
guidance and details on handling thought signatures for Gemini 3.

### Inspecting thought signatures

While not necessary for implementation, you can inspect the response to see the
`thought_signature` for debugging or educational purposes.

### Python

    import base64
    # After receiving a response from a model with thinking enabled
    # response = client.models.generate_content(...)

    # The signature is attached to the response part containing the function call
    part = response.candidates[0].content.parts[0]
    if part.thought_signature:
      print(base64.b64encode(part.thought_signature).decode("utf-8"))

### JavaScript

    // After receiving a response from a model with thinking enabled
    // const response = await ai.models.generateContent(...)

    // The signature is attached to the response part containing the function call
    const part = response.candidates[0].content.parts[0];
    if (part.thoughtSignature) {
      console.log(part.thoughtSignature);
    }

Learn more about limitations and usage of thought signatures, and about thinking
models in general, on the [Thinking](https://ai.google.dev/gemini-api/docs/thinking#signatures) page.

## Parallel function calling

In addition to single turn function calling, you can also call multiple
functions at once. Parallel function calling lets you execute multiple functions
at once and is used when the functions are not dependent on each other. This is
useful in scenarios like gathering data from multiple independent sources, such
as retrieving customer details from different databases or checking inventory
levels across various warehouses or performing multiple actions such as
converting your apartment into a disco.

### Python

    power_disco_ball = {
        "name": "power_disco_ball",
        "description": "Powers the spinning disco ball.",
        "parameters": {
            "type": "object",
            "properties": {
                "power": {
                    "type": "boolean",
                    "description": "Whether to turn the disco ball on or off.",
                }
            },
            "required": ["power"],
        },
    }

    start_music = {
        "name": "start_music",
        "description": "Play some music matching the specified parameters.",
        "parameters": {
            "type": "object",
            "properties": {
                "energetic": {
                    "type": "boolean",
                    "description": "Whether the music is energetic or not.",
                },
                "loud": {
                    "type": "boolean",
                    "description": "Whether the music is loud or not.",
                },
            },
            "required": ["energetic", "loud"],
        },
    }

    dim_lights = {
        "name": "dim_lights",
        "description": "Dim the lights.",
        "parameters": {
            "type": "object",
            "properties": {
                "brightness": {
                    "type": "number",
                    "description": "The brightness of the lights, 0.0 is off, 1.0 is full.",
                }
            },
            "required": ["brightness"],
        },
    }

### JavaScript

    import { Type } from '@google/genai';

    const powerDiscoBall = {
      name: 'power_disco_ball',
      description: 'Powers the spinning disco ball.',
      parameters: {
        type: Type.OBJECT,
        properties: {
          power: {
            type: Type.BOOLEAN,
            description: 'Whether to turn the disco ball on or off.'
          }
        },
        required: ['power']
      }
    };

    const startMusic = {
      name: 'start_music',
      description: 'Play some music matching the specified parameters.',
      parameters: {
        type: Type.OBJECT,
        properties: {
          energetic: {
            type: Type.BOOLEAN,
            description: 'Whether the music is energetic or not.'
          },
          loud: {
            type: Type.BOOLEAN,
            description: 'Whether the music is loud or not.'
          }
        },
        required: ['energetic', 'loud']
      }
    };

    const dimLights = {
      name: 'dim_lights',
      description: 'Dim the lights.',
      parameters: {
        type: Type.OBJECT,
        properties: {
          brightness: {
            type: Type.NUMBER,
            description: 'The brightness of the lights, 0.0 is off, 1.0 is full.'
          }
        },
        required: ['brightness']
      }
    };

Configure the function calling mode to allow using all of the specified tools.
To learn more, you can read about
[configuring function calling](https://ai.google.dev/gemini-api/docs/function-calling#function_calling_modes).

### Python

    from google import genai
    from google.genai import types

    # Configure the client and tools
    client = genai.Client()
    house_tools = [
        types.Tool(function_declarations=[power_disco_ball, start_music, dim_lights])
    ]
    config = types.GenerateContentConfig(
        tools=house_tools,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(
            disable=True
        ),
        # Force the model to call 'any' function, instead of chatting.
        tool_config=types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(mode='ANY')
        ),
    )

    chat = client.chats.create(model="gemini-3-flash-preview", config=config)
    response = chat.send_message("Turn this place into a party!")

    # Print out each of the function calls requested from this single call
    print("Example 1: Forced function calling")
    for fn in response.function_calls:
        args = ", ".join(f"{key}={val}" for key, val in fn.args.items())
        print(f"{fn.name}({args})")

### JavaScript

    import { GoogleGenAI } from '@google/genai';

    // Set up function declarations
    const houseFns = [powerDiscoBall, startMusic, dimLights];

    const config = {
        tools: [{
            functionDeclarations: houseFns
        }],
        // Force the model to call 'any' function, instead of chatting.
        toolConfig: {
            functionCallingConfig: {
                mode: 'any'
            }
        }
    };

    // Configure the client
    const ai = new GoogleGenAI({});

    // Create a chat session
    const chat = ai.chats.create({
        model: 'gemini-3-flash-preview',
        config: config
    });
    const response = await chat.sendMessage({message: 'Turn this place into a party!'});

    // Print out each of the function calls requested from this single call
    console.log("Example 1: Forced function calling");
    for (const fn of response.functionCalls) {
        const args = Object.entries(fn.args)
            .map(([key, val]) => `${key}=${val}`)
            .join(', ');
        console.log(`${fn.name}(${args})`);
    }

Each of the printed results reflects a single function call that the model has
requested. To send the results back, include the responses in the same order as
they were requested.

The Python SDK supports [automatic function calling](https://ai.google.dev/gemini-api/docs/function-calling#automatic_function_calling_python_only),
which automatically converts Python functions to declarations, handles the
function call execution and response cycle for you. Following is an example for
the disco use case.
| **Note:** Automatic Function Calling is a Python SDK only feature at the moment.

### Python

    from google import genai
    from google.genai import types

    # Actual function implementations
    def power_disco_ball_impl(power: bool) -> dict:
        """Powers the spinning disco ball.

        Args:
            power: Whether to turn the disco ball on or off.

        Returns:
            A status dictionary indicating the current state.
        """
        return {"status": f"Disco ball powered {'on' if power else 'off'}"}

    def start_music_impl(energetic: bool, loud: bool) -> dict:
        """Play some music matching the specified parameters.

        Args:
            energetic: Whether the music is energetic or not.
            loud: Whether the music is loud or not.

        Returns:
            A dictionary containing the music settings.
        """
        music_type = "energetic" if energetic else "chill"
        volume = "loud" if loud else "quiet"
        return {"music_type": music_type, "volume": volume}

    def dim_lights_impl(brightness: float) -> dict:
        """Dim the lights.

        Args:
            brightness: The brightness of the lights, 0.0 is off, 1.0 is full.

        Returns:
            A dictionary containing the new brightness setting.
        """
        return {"brightness": brightness}

    # Configure the client
    client = genai.Client()
    config = types.GenerateContentConfig(
        tools=[power_disco_ball_impl, start_music_impl, dim_lights_impl]
    )

    # Make the request
    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents="Do everything you need to this place into party!",
        config=config,
    )

    print("\nExample 2: Automatic function calling")
    print(response.text)
    # I've turned on the disco ball, started playing loud and energetic music, and dimmed the lights to 50% brightness. Let's get this party started!

## Compositional function calling

Compositional or sequential function calling allows Gemini to chain multiple
function calls together to fulfill a complex request. For example, to answer
"Get the temperature in my current location", the Gemini API might first invoke
a `get_current_location()` function followed by a `get_weather()` function that
takes the location as a parameter.

The following example demonstrates how to implement compositional function
calling using the Python SDK and automatic function calling.

### Python

This example uses the automatic function calling feature of the
`google-genai` Python SDK. The SDK automatically converts the Python
functions to the required schema, executes the function calls when requested
by the model, and sends the results back to the model to complete the task.

    import os
    from google import genai
    from google.genai import types

    # Example Functions
    def get_weather_forecast(location: str) -> dict:
        """Gets the current weather temperature for a given location."""
        print(f"Tool Call: get_weather_forecast(location={location})")
        # TODO: Make API call
        print("Tool Response: {'temperature': 25, 'unit': 'celsius'}")
        return {"temperature": 25, "unit": "celsius"}  # Dummy response

    def set_thermostat_temperature(temperature: int) -> dict:
        """Sets the thermostat to a desired temperature."""
        print(f"Tool Call: set_thermostat_temperature(temperature={temperature})")
        # TODO: Interact with a thermostat API
        print("Tool Response: {'status': 'success'}")
        return {"status": "success"}

    # Configure the client and model
    client = genai.Client()
    config = types.GenerateContentConfig(
        tools=[get_weather_forecast, set_thermostat_temperature]
    )

    # Make the request
    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents="If it's warmer than 20°C in London, set the thermostat to 20°C, otherwise set it to 18°C.",
        config=config,
    )

    # Print the final, user-facing response
    print(response.text)

**Expected Output**

When you run the code, you will see the SDK orchestrating the function
calls. The model first calls `get_weather_forecast`, receives the
temperature, and then calls `set_thermostat_temperature` with the correct
value based on the logic in the prompt.

    Tool Call: get_weather_forecast(location=London)
    Tool Response: {'temperature': 25, 'unit': 'celsius'}
    Tool Call: set_thermostat_temperature(temperature=20)
    Tool Response: {'status': 'success'}
    OK. I've set the thermostat to 20°C.

### JavaScript

This example shows how to use JavaScript/TypeScript SDK to do comopositional
function calling using a manual execution loop.

    import { GoogleGenAI, Type } from "@google/genai";

    // Configure the client
    const ai = new GoogleGenAI({});

    // Example Functions
    function get_weather_forecast({ location }) {
      console.log(`Tool Call: get_weather_forecast(location=${location})`);
      // TODO: Make API call
      console.log("Tool Response: {'temperature': 25, 'unit': 'celsius'}");
      return { temperature: 25, unit: "celsius" };
    }

    function set_thermostat_temperature({ temperature }) {
      console.log(
        `Tool Call: set_thermostat_temperature(temperature=${temperature})`,
      );
      // TODO: Make API call
      console.log("Tool Response: {'status': 'success'}");
      return { status: "success" };
    }

    const toolFunctions = {
      get_weather_forecast,
      set_thermostat_temperature,
    };

    const tools = [
      {
        functionDeclarations: [
          {
            name: "get_weather_forecast",
            description:
              "Gets the current weather temperature for a given location.",
            parameters: {
              type: Type.OBJECT,
              properties: {
                location: {
                  type: Type.STRING,
                },
              },
              required: ["location"],
            },
          },
          {
            name: "set_thermostat_temperature",
            description: "Sets the thermostat to a desired temperature.",
            parameters: {
              type: Type.OBJECT,
              properties: {
                temperature: {
                  type: Type.NUMBER,
                },
              },
              required: ["temperature"],
            },
          },
        ],
      },
    ];

    // Prompt for the model
    let contents = [
      {
        role: "user",
        parts: [
          {
            text: "If it's warmer than 20°C in London, set the thermostat to 20°C, otherwise set it to 18°C.",
          },
        ],
      },
    ];

    // Loop until the model has no more function calls to make
    while (true) {
      const result = await ai.models.generateContent({
        model: "gemini-3-flash-preview",
        contents,
        config: { tools },
      });

      if (result.functionCalls && result.functionCalls.length > 0) {
        const functionCall = result.functionCalls[0];

        const { name, args } = functionCall;

        if (!toolFunctions[name]) {
          throw new Error(`Unknown function call: ${name}`);
        }

        // Call the function and get the response.
        const toolResponse = toolFunctions[name](args);

        const functionResponsePart = {
          name: functionCall.name,
          response: {
            result: toolResponse,
          },
        };

        // Send the function response back to the model.
        contents.push({
          role: "model",
          parts: [
            {
              functionCall: functionCall,
            },
          ],
        });
        contents.push({
          role: "user",
          parts: [
            {
              functionResponse: functionResponsePart,
            },
          ],
        });
      } else {
        // No more function calls, break the loop.
        console.log(result.text);
        break;
      }
    }

**Expected Output**

When you run the code, you will see the SDK orchestrating the function
calls. The model first calls `get_weather_forecast`, receives the
temperature, and then calls `set_thermostat_temperature` with the correct
value based on the logic in the prompt.

    Tool Call: get_weather_forecast(location=London)
    Tool Response: {'temperature': 25, 'unit': 'celsius'}
    Tool Call: set_thermostat_temperature(temperature=20)
    Tool Response: {'status': 'success'}
    OK. It's 25°C in London, so I've set the thermostat to 20°C.

Compositional function calling is a native [Live
API](https://ai.google.dev/gemini-api/docs/live) feature. This means Live API
can handle the function calling similar to the Python SDK.

### Python

    # Light control schemas
    turn_on_the_lights_schema = {'name': 'turn_on_the_lights'}
    turn_off_the_lights_schema = {'name': 'turn_off_the_lights'}

    prompt = """
      Hey, can you write run some python code to turn on the lights, wait 10s and then turn off the lights?
      """

    tools = [
        {'code_execution': {}},
        {'function_declarations': [turn_on_the_lights_schema, turn_off_the_lights_schema]}
    ]

    await run(prompt, tools=tools, modality="AUDIO")

### JavaScript

    // Light control schemas
    const turnOnTheLightsSchema = { name: 'turn_on_the_lights' };
    const turnOffTheLightsSchema = { name: 'turn_off_the_lights' };

    const prompt = `
      Hey, can you write run some python code to turn on the lights, wait 10s and then turn off the lights?
    `;

    const tools = [
      { codeExecution: {} },
      { functionDeclarations: [turnOnTheLightsSchema, turnOffTheLightsSchema] }
    ];

    await run(prompt, tools=tools, modality="AUDIO")

## Function calling modes

The Gemini API lets you control how the model uses the provided tools
(function declarations). Specifically, you can set the mode within
the.`function_calling_config`.

- `AUTO (Default)`: The model decides whether to generate a natural language response or suggest a function call based on the prompt and context. This is the most flexible mode and recommended for most scenarios.
- `ANY`: The model is constrained to always predict a function call and guarantees function schema adherence. If `allowed_function_names` is not specified, the model can choose from any of the provided function declarations. If `allowed_function_names` is provided as a list, the model can only choose from the functions in that list. Use this mode when you require a function call response to every prompt (if applicable).
- `NONE`: The model is *prohibited* from making function calls. This is equivalent to sending a request without any function declarations. Use this to temporarily disable function calling without removing your tool definitions.
- `VALIDATED` (Preview): The model is constrained to predict either function
  calls or natural language, and ensures function schema adherence. If
  `allowed_function_names` is not provided, the model picks from all of the
  available function declarations. If `allowed_function_names` is provided, the
  model picks from the set of allowed functions.

### Python

    from google.genai import types

    # Configure function calling mode
    tool_config = types.ToolConfig(
        function_calling_config=types.FunctionCallingConfig(
            mode="ANY", allowed_function_names=["get_current_temperature"]
        )
    )

    # Create the generation config
    config = types.GenerateContentConfig(
        tools=[tools],  # not defined here.
        tool_config=tool_config,
    )

### JavaScript

    import { FunctionCallingConfigMode } from '@google/genai';

    // Configure function calling mode
    const toolConfig = {
      functionCallingConfig: {
        mode: FunctionCallingConfigMode.ANY,
        allowedFunctionNames: ['get_current_temperature']
      }
    };

    // Create the generation config
    const config = {
      tools: tools, // not defined here.
      toolConfig: toolConfig,
    };

## Automatic function calling (Python only)

When using the Python SDK, you can provide Python functions directly as tools.
The SDK converts these functions into declarations, manages the function call
execution, and handles the response cycle for you. Define your function with
type hints and a docstring. For optimal results, it is recommended to use
[Google-style docstrings.](https://google.github.io/styleguide/pyguide.html#383-functions-and-methods)
The SDK will then automatically:

1. Detect function call responses from the model.
2. Call the corresponding Python function in your code.
3. Send the function's response back to the model.
4. Return the model's final text response.

The SDK currently does not parse argument descriptions into the property
description slots of the generated function declaration. Instead, it sends the
entire docstring as the top-level function description.

### Python

    from google import genai
    from google.genai import types

    # Define the function with type hints and docstring
    def get_current_temperature(location: str) -> dict:
        """Gets the current temperature for a given location.

        Args:
            location: The city and state, e.g. San Francisco, CA

        Returns:
            A dictionary containing the temperature and unit.
        """
        # ... (implementation) ...
        return {"temperature": 25, "unit": "Celsius"}

    # Configure the client
    client = genai.Client()
    config = types.GenerateContentConfig(
        tools=[get_current_temperature]
    )  # Pass the function itself

    # Make the request
    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents="What's the temperature in Boston?",
        config=config,
    )

    print(response.text)  # The SDK handles the function call and returns the final text

You can disable automatic function calling with:

### Python

    config = types.GenerateContentConfig(
        tools=[get_current_temperature],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
    )

### Automatic function schema declaration

The API is able to describe any of the following types. `Pydantic` types are
allowed, as long as the fields defined on them are also composed of allowed
types. Dict types (like `dict[str: int]`) are not well supported here, don't
use them.

### Python

    AllowedType = (
      int | float | bool | str | list['AllowedType'] | pydantic.BaseModel)

To see what the inferred schema looks like, you can convert it using
[`from_callable`](https://googleapis.github.io/python-genai/genai.html#genai.types.FunctionDeclaration.from_callable):

### Python

    from google import genai
    from google.genai import types

    def multiply(a: float, b: float):
        """Returns a * b."""
        return a * b

    client = genai.Client()
    fn_decl = types.FunctionDeclaration.from_callable(callable=multiply, client=client)

    # to_json_dict() provides a clean JSON representation.
    print(fn_decl.to_json_dict())

## Multi-tool use: Combine native tools with function calling

You can enable multiple tools combining native tools with
function calling at the same time. Here's an example that enables two tools,
[Grounding with Google Search](https://ai.google.dev/gemini-api/docs/grounding) and
[code execution](https://ai.google.dev/gemini-api/docs/code-execution), in a request using the
[Live API](https://ai.google.dev/gemini-api/docs/live).
| **Note:** Multi-tool use is a-[Live API](https://ai.google.dev/gemini-api/docs/live) only feature at the moment. The `run()` function declaration, which handles the asynchronous websocket setup, is omitted for brevity.

### Python

    # Multiple tasks example - combining lights, code execution, and search
    prompt = """
      Hey, I need you to do three things for me.

        1.  Turn on the lights.
        2.  Then compute the largest prime palindrome under 100000.
        3.  Then use Google Search to look up information about the largest earthquake in California the week of Dec 5 2024.

      Thanks!
      """

    tools = [
        {'google_search': {}},
        {'code_execution': {}},
        {'function_declarations': [turn_on_the_lights_schema, turn_off_the_lights_schema]} # not defined here.
    ]

    # Execute the prompt with specified tools in audio modality
    await run(prompt, tools=tools, modality="AUDIO")

### JavaScript

    // Multiple tasks example - combining lights, code execution, and search
    const prompt = `
      Hey, I need you to do three things for me.

        1.  Turn on the lights.
        2.  Then compute the largest prime palindrome under 100000.
        3.  Then use Google Search to look up information about the largest earthquake in California the week of Dec 5 2024.

      Thanks!
    `;

    const tools = [
      { googleSearch: {} },
      { codeExecution: {} },
      { functionDeclarations: [turnOnTheLightsSchema, turnOffTheLightsSchema] } // not defined here.
    ];

    // Execute the prompt with specified tools in audio modality
    await run(prompt, {tools: tools, modality: "AUDIO"});

Python developers can try this out in the [Live API Tool Use
notebook](https://colab.research.google.com/github/google-gemini/cookbook/blob/main/quickstarts/Get_started_LiveAPI_tools.ipynb).

## Multimodal function responses

| **Note:** This feature is available for [Gemini 3](https://ai.google.dev/gemini-api/docs/gemini-3) series models.

For Gemini 3 series models, you can include multimodal content in
the function response parts that you send to the model. The model can process
this multimodal content in its next turn to produce a more informed response.
The following MIME types are supported for multimodal content in function
responses:

- **Images** : `image/png`, `image/jpeg`, `image/webp`
- **Documents** : `application/pdf`, `text/plain`

To include multimodal data in a function response, include it as one or more
parts nested within the `functionResponse` part. Each multimodal part must
contain `inlineData`. If you reference a multimodal part from
within the structured `response` field, it must contain a unique `displayName`.

You can also reference a multimodal part from within the structured `response`
field of the `functionResponse` part by using the JSON reference format
`{"$ref": "<displayName>"}`. The model substitutes the reference with the
multimodal content when processing the response. Each `displayName` can only be
referenced once in the structured `response` field.

The following example shows a message containing a `functionResponse` for a
function named `get_image` and a nested part containing image data with
`displayName: "instrument.jpg"`. The `functionResponse`'s `response` field
references this image part:

### Python

    from google import genai
    from google.genai import types

    import requests

    client = genai.Client()

    # This is a manual, two turn multimodal function calling workflow:

    # 1. Define the function tool
    get_image_declaration = types.FunctionDeclaration(
      name="get_image",
      description="Retrieves the image file reference for a specific order item.",
      parameters={
          "type": "object",
          "properties": {
              "item_name": {
                  "type": "string",
                  "description": "The name or description of the item ordered (e.g., 'instrument')."
              }
          },
          "required": ["item_name"],
      },
    )
    tool_config = types.Tool(function_declarations=[get_image_declaration])

    # 2. Send a message that triggers the tool
    prompt = "Show me the instrument I ordered last month."
    response_1 = client.models.generate_content(
      model="gemini-3-flash-preview",
      contents=[prompt],
      config=types.GenerateContentConfig(
          tools=[tool_config],
      )
    )

    # 3. Handle the function call
    function_call = response_1.function_calls[0]
    requested_item = function_call.args["item_name"]
    print(f"Model wants to call: {function_call.name}")

    # Execute your tool (e.g., call an API)
    # (This is a mock response for the example)
    print(f"Calling external tool for: {requested_item}")

    function_response_data = {
      "image_ref": {"$ref": "instrument.jpg"},
    }
    image_path = "https://goo.gle/instrument-img"
    image_bytes = requests.get(image_path).content
    function_response_multimodal_data = types.FunctionResponsePart(
      inline_data=types.FunctionResponseBlob(
        mime_type="image/jpeg",
        display_name="instrument.jpg",
        data=image_bytes,
      )
    )

    # 4. Send the tool's result back
    # Append this turn's messages to history for a final response.
    history = [
      types.Content(role="user", parts=[types.Part(text=prompt)]),
      response_1.candidates[0].content,
      types.Content(
        role="tool",
        parts=[
            types.Part.from_function_response(
              name=function_call.name,
              response=function_response_data,
              parts=[function_response_multimodal_data]
            )
        ],
      )
    ]

    response_2 = client.models.generate_content(
      model="gemini-3-flash-preview",
      contents=history,
      config=types.GenerateContentConfig(
          tools=[tool_config],
          thinking_config=types.ThinkingConfig(include_thoughts=True)
      ),
    )

    print(f"\nFinal model response: {response_2.text}")

### JavaScript

    import { GoogleGenAI, Type } from '@google/genai';

    const client = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });

    // This is a manual, two turn multimodal function calling workflow:
    // 1. Define the function tool
    const getImageDeclaration = {
      name: 'get_image',
      description: 'Retrieves the image file reference for a specific order item.',
      parameters: {
        type: Type.OBJECT,
        properties: {
          item_name: {
            type: Type.STRING,
            description: "The name or description of the item ordered (e.g., 'instrument').",
          },
        },
        required: ['item_name'],
      },
    };

    const toolConfig = {
      functionDeclarations: [getImageDeclaration],
    };

    // 2. Send a message that triggers the tool
    const prompt = 'Show me the instrument I ordered last month.';
    const response1 = await client.models.generateContent({
      model: 'gemini-3-flash-preview',
      contents: prompt,
      config: {
        tools: [toolConfig],
      },
    });

    // 3. Handle the function call
    const functionCall = response1.functionCalls[0];
    const requestedItem = functionCall.args.item_name;
    console.log(`Model wants to call: ${functionCall.name}`);

    // Execute your tool (e.g., call an API)
    // (This is a mock response for the example)
    console.log(`Calling external tool for: ${requestedItem}`);

    const functionResponseData = {
      image_ref: { $ref: 'instrument.jpg' },
    };

    const imageUrl = "https://goo.gle/instrument-img";
    const response = await fetch(imageUrl);
    const imageArrayBuffer = await response.arrayBuffer();
    const base64ImageData = Buffer.from(imageArrayBuffer).toString('base64');

    const functionResponseMultimodalData = {
      inlineData: {
        mimeType: 'image/jpeg',
        displayName: 'instrument.jpg',
        data: base64ImageData,
      },
    };

    // 4. Send the tool's result back
    // Append this turn's messages to history for a final response.
    const history = [
      { role: 'user', parts: [{ text: prompt }] },
      response1.candidates[0].content,
      {
        role: 'tool',
        parts: [
          {
            functionResponse: {
              name: functionCall.name,
              response: functionResponseData,
              parts: [functionResponseMultimodalData],
            },
          },
        ],
      },
    ];

    const response2 = await client.models.generateContent({
      model: 'gemini-3-flash-preview',
      contents: history,
      config: {
        tools: [toolConfig],
        thinkingConfig: { includeThoughts: true },
      },
    });

    console.log(`\nFinal model response: ${response2.text}`);

### REST

    IMG_URL="https://goo.gle/instrument-img"

    MIME_TYPE=$(curl -sIL "$IMG_URL" | grep -i '^content-type:' | awk -F ': ' '{print $2}' | sed 's/\r$//' | head -n 1)
    if [[ -z "$MIME_TYPE" || ! "$MIME_TYPE" == image/* ]]; then
      MIME_TYPE="image/jpeg"
    fi

    # Check for macOS
    if [[ "$(uname)" == "Darwin" ]]; then
      IMAGE_B64=$(curl -sL "$IMG_URL" | base64 -b 0)
    elif [[ "$(base64 --version 2>&1)" = *"FreeBSD"* ]]; then
      IMAGE_B64=$(curl -sL "$IMG_URL" | base64)
    else
      IMAGE_B64=$(curl -sL "$IMG_URL" | base64 -w0)
    fi

    curl "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent" \
      -H "x-goog-api-key: $GEMINI_API_KEY" \
      -H 'Content-Type: application/json' \
      -X POST \
      -d '{
        "contents": [
          ...,
          {
            "role": "user",
            "parts": [
            {
                "functionResponse": {
                  "name": "get_image",
                  "response": {
                    "image_ref": {
                      "$ref": "instrument.jpg"
                    }
                  },
                  "parts": [
                    {
                      "inlineData": {
                        "displayName": "instrument.jpg",
                        "mimeType":"'"$MIME_TYPE"'",
                        "data": "'"$IMAGE_B64"'"
                      }
                    }
                  ]
                }
              }
            ]
          }
        ]
      }'

## Function calling with Structured output

| **Note:** This feature is available for [Gemini 3](https://ai.google.dev/gemini-api/docs/gemini-3) series models.

For Gemini 3 series models, you can use function calling with [structured output](https://ai.google.dev/gemini-api/docs/structured-output). This lets the model predict function calls or outputs that adhere to a specific schema. As a result, you receive consistently formatted responses when the model doesn't generate function calls.

## Model context protocol (MCP)

[Model Context Protocol (MCP)](https://modelcontextprotocol.io/introduction) is
an open standard for connecting AI applications with external tools and data.
MCP provides a common protocol for models to access context, such as functions
(tools), data sources (resources), or predefined prompts.

The Gemini SDKs have built-in support for the MCP, reducing boilerplate code and
offering
[automatic tool calling](https://ai.google.dev/gemini-api/docs/function-calling#automatic_function_calling_python_only)
for MCP tools. When the model generates an MCP tool call, the Python and
JavaScript client SDK can automatically execute the MCP tool and send the
response back to the model in a subsequent request, continuing this loop until
no more tool calls are made by the model.

Here, you can find an example of how to use a local MCP server with Gemini and
`mcp` SDK.

### Python

Make sure the latest version of the
[`mcp` SDK](https://modelcontextprotocol.io/introduction) is installed on
your platform of choice.

    pip install mcp

| **Note:** Python supports automatic tool calling by passing in the `ClientSession` into the `tools` parameters. If you want to disable it, you can provide `automatic_function_calling` with disabled `True`.

    import os
    import asyncio
    from datetime import datetime
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from google import genai

    client = genai.Client()

    # Create server parameters for stdio connection
    server_params = StdioServerParameters(
        command="npx",  # Executable
        args=["-y", "@philschmid/weather-mcp"],  # MCP Server
        env=None,  # Optional environment variables
    )

    async def run():
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                # Prompt to get the weather for the current day in London.
                prompt = f"What is the weather in London in {datetime.now().strftime('%Y-%m-%d')}?"

                # Initialize the connection between client and server
                await session.initialize()

                # Send request to the model with MCP function declarations
                response = await client.aio.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=genai.types.GenerateContentConfig(
                        temperature=0,
                        tools=[session],  # uses the session, will automatically call the tool
                        # Uncomment if you **don't** want the SDK to automatically call the tool
                        # automatic_function_calling=genai.types.AutomaticFunctionCallingConfig(
                        #     disable=True
                        # ),
                    ),
                )
                print(response.text)

    # Start the asyncio event loop and run the main function
    asyncio.run(run())

### JavaScript

Make sure the latest version of the `mcp` SDK is installed on your platform
of choice.

    npm install @modelcontextprotocol/sdk

| **Note:** JavaScript supports automatic tool calling by wrapping the `client` with `mcpToTool`. If you want to disable it, you can provide `automaticFunctionCalling` with disabled `true`.

    import { GoogleGenAI, FunctionCallingConfigMode , mcpToTool} from '@google/genai';
    import { Client } from "@modelcontextprotocol/sdk/client/index.js";
    import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

    // Create server parameters for stdio connection
    const serverParams = new StdioClientTransport({
      command: "npx", // Executable
      args: ["-y", "@philschmid/weather-mcp"] // MCP Server
    });

    const client = new Client(
      {
        name: "example-client",
        version: "1.0.0"
      }
    );

    // Configure the client
    const ai = new GoogleGenAI({});

    // Initialize the connection between client and server
    await client.connect(serverParams);

    // Send request to the model with MCP tools
    const response = await ai.models.generateContent({
      model: "gemini-2.5-flash",
      contents: `What is the weather in London in ${new Date().toLocaleDateString()}?`,
      config: {
        tools: [mcpToTool(client)],  // uses the session, will automatically call the tool
        // Uncomment if you **don't** want the sdk to automatically call the tool
        // automaticFunctionCalling: {
        //   disable: true,
        // },
      },
    });
    console.log(response.text)

    // Close the connection
    await client.close();

### Limitations with built-in MCP support

Built-in MCP support is a [experimental](https://ai.google.dev/gemini-api/docs/models#preview)
feature in our SDKs and has the following limitations:

- Only tools are supported, not resources nor prompts
- It is available for the Python and JavaScript/TypeScript SDK.
- Breaking changes might occur in future releases.

Manual integration of MCP servers is always an option if these limit what you're
building.

## Supported models

This section lists models and their function calling capabilities. Experimental
models are not included. You can find a comprehensive capabilities overview on
the [model overview](https://ai.google.dev/gemini-api/docs/models) page.

| Model | Function Calling | Parallel Function Calling | Compositional Function Calling |
|---|---|---|---|
| Gemini 3 Pro | ✔️ | ✔️ | ✔️ |
| Gemini 3 Flash | ✔️ | ✔️ | ✔️ |
| Gemini 2.5 Pro | ✔️ | ✔️ | ✔️ |
| Gemini 2.5 Flash | ✔️ | ✔️ | ✔️ |
| Gemini 2.5 Flash-Lite | ✔️ | ✔️ | ✔️ |
| Gemini 2.0 Flash | ✔️ | ✔️ | ✔️ |
| Gemini 2.0 Flash-Lite | X | X | X |

## Best practices

- **Function and Parameter Descriptions:** Be extremely clear and specific in your descriptions. The model relies on these to choose the correct function and provide appropriate arguments.
- **Naming:** Use descriptive function names (without spaces, periods, or dashes).
- **Strong Typing:** Use specific types (integer, string, enum) for parameters to reduce errors. If a parameter has a limited set of valid values, use an enum.
- **Tool Selection:** While the model can use an arbitrary number of tools, providing too many can increase the risk of selecting an incorrect or suboptimal tool. For best results, aim to provide only the relevant tools for the context or task, ideally keeping the active set to a maximum of 10-20. Consider dynamic tool selection based on conversation context if you have a large total number of tools.
- **Prompt Engineering:**
  - Provide context: Tell the model its role (e.g., "You are a helpful weather assistant.").
  - Give instructions: Specify how and when to use functions (e.g., "Don't guess dates; always use a future date for forecasts.").
  - Encourage clarification: Instruct the model to ask clarifying questions if needed.
  - See [Agentic workflows](https://ai.google.dev/gemini-api/docs/prompting-strategies#agentic-workflows) for further strategies on designing these prompts. Here is an example of a tested [system instruction](https://ai.google.dev/gemini-api/docs/prompting-strategies#agentic-si-template).
- **Temperature:** Use a low temperature (e.g., 0) for more deterministic and
  reliable function calls.

  | When using Gemini 3 models, we strongly recommend keeping the `temperature` at its default value of 1.0. Changing the temperature (setting it below 1.0) may lead to unexpected behavior, such as looping or degraded performance, particularly in complex mathematical or reasoning tasks.
- **Validation:** If a function call has significant consequences (e.g.,
  placing an order), validate the call with the user before executing it.

- **Check Finish Reason:** Always check the [`finishReason`](https://ai.google.dev/api/generate-content#FinishReason)
  in the model's response to handle cases where the model failed to generate a
  valid function call.

- **Error Handling**: Implement robust error handling in your functions to
  gracefully handle unexpected inputs or API failures. Return informative
  error messages that the model can use to generate helpful responses to the
  user.

- **Security:** Be mindful of security when calling external APIs. Use
  appropriate authentication and authorization mechanisms. Avoid exposing
  sensitive data in function calls.

- **Token Limits:** Function descriptions and parameters count towards your
  input token limit. If you're hitting token limits, consider limiting the
  number of functions or the length of the descriptions, break down complex
  tasks into smaller, more focused function sets.

## Notes and limitations

- Only a [subset of the OpenAPI
  schema](https://ai.google.dev/api/caching#FunctionDeclaration) is supported.
- For `ANY` mode, the API may reject very large or deeply nested schemas. If you encounter errors, try simplifying your function parameter and response schemas by shortening property names, reducing nesting, or limiting the number of function declarations.
- Supported parameter types in Python are limited.
- Automatic function calling is a Python SDK feature only.


The Gemini API supports content generation with images, audio, code, tools, and more. For details on each of these features, read on and check out the task-focused sample code, or read the comprehensive guides.

- [Text generation](https://ai.google.dev/gemini-api/docs/text-generation)
- [Vision](https://ai.google.dev/gemini-api/docs/vision)
- [Audio](https://ai.google.dev/gemini-api/docs/audio)
- [Embeddings](https://ai.google.dev/gemini-api/docs/embeddings)
- [Long context](https://ai.google.dev/gemini-api/docs/long-context)
- [Code execution](https://ai.google.dev/gemini-api/docs/code-execution)
- [JSON Mode](https://ai.google.dev/gemini-api/docs/json-mode)
- [Function calling](https://ai.google.dev/gemini-api/docs/function-calling)
- [System instructions](https://ai.google.dev/gemini-api/docs/system-instructions)

## Method: models.generateContent

- [Endpoint](https://ai.google.dev/api/generate-content#body.HTTP_TEMPLATE)
- [Path parameters](https://ai.google.dev/api/generate-content#body.PATH_PARAMETERS)
- [Request body](https://ai.google.dev/api/generate-content#body.request_body)
  - [JSON representation](https://ai.google.dev/api/generate-content#body.request_body.SCHEMA_REPRESENTATION)
- [Response body](https://ai.google.dev/api/generate-content#body.response_body)
- [Authorization scopes](https://ai.google.dev/api/generate-content#body.aspect)
- [Example request](https://ai.google.dev/api/generate-content#body.codeSnippets)
  - [Text](https://ai.google.dev/api/generate-content#body.codeSnippets.group)
  - [Image](https://ai.google.dev/api/generate-content#body.codeSnippets.group_1)
  - [Audio](https://ai.google.dev/api/generate-content#body.codeSnippets.group_2)
  - [Video](https://ai.google.dev/api/generate-content#body.codeSnippets.group_3)
  - [PDF](https://ai.google.dev/api/generate-content#body.codeSnippets.group_4)
  - [Chat](https://ai.google.dev/api/generate-content#body.codeSnippets.group_5)
  - [Cache](https://ai.google.dev/api/generate-content#body.codeSnippets.group_6)
  - [Tuned Model](https://ai.google.dev/api/generate-content#body.codeSnippets.group_7)
  - [JSON Mode](https://ai.google.dev/api/generate-content#body.codeSnippets.group_8)
  - [Code execution](https://ai.google.dev/api/generate-content#body.codeSnippets.group_9)
  - [Function Calling](https://ai.google.dev/api/generate-content#body.codeSnippets.group_10)
  - [Generation config](https://ai.google.dev/api/generate-content#body.codeSnippets.group_11)
  - [Safety Settings](https://ai.google.dev/api/generate-content#body.codeSnippets.group_12)
  - [System Instruction](https://ai.google.dev/api/generate-content#body.codeSnippets.group_13)

Generates a model response given an input `GenerateContentRequest`. Refer to the [text generation guide](https://ai.google.dev/gemini-api/docs/text-generation) for detailed usage information. Input capabilities differ between models, including tuned models. Refer to the [model guide](https://ai.google.dev/gemini-api/docs/models/gemini) and [tuning guide](https://ai.google.dev/gemini-api/docs/model-tuning) for details.

### Endpoint

post `https:``/``/generativelanguage.googleapis.com``/v1beta``/{model=models``/*}:generateContent`

### Path parameters

`model` `string`
Required. The name of the `Model` to use for generating the completion.

Format: `models/{model}`. It takes the form `models/{model}`.

### Request body

The request body contains data with the following structure:
Fields `contents[]` `object (`[Content](https://ai.google.dev/api/caching#Content)`)`
Required. The content of the current conversation with the model.

For single-turn queries, this is a single instance. For multi-turn queries like [chat](https://ai.google.dev/gemini-api/docs/text-generation#chat), this is a repeated field that contains the conversation history and the latest request.
`tools[]` `object (`[Tool](https://ai.google.dev/api/caching#Tool)`)`
Optional. A list of `Tools` the `Model` may use to generate the next response.

A `Tool` is a piece of code that enables the system to interact with external systems to perform an action, or set of actions, outside of knowledge and scope of the `Model`. Supported `Tool`s are `Function` and `codeExecution`. Refer to the [Function calling](https://ai.google.dev/gemini-api/docs/function-calling) and the [Code execution](https://ai.google.dev/gemini-api/docs/code-execution) guides to learn more.
`toolConfig` `object (`[ToolConfig](https://ai.google.dev/api/caching#ToolConfig)`)`
Optional. Tool configuration for any `Tool` specified in the request. Refer to the [Function calling guide](https://ai.google.dev/gemini-api/docs/function-calling#function_calling_mode) for a usage example.
`safetySettings[]` `object (`[SafetySetting](https://ai.google.dev/api/generate-content#v1beta.SafetySetting)`)`
Optional. A list of unique `SafetySetting` instances for blocking unsafe content.

This will be enforced on the `GenerateContentRequest.contents` and `GenerateContentResponse.candidates`. There should not be more than one setting for each `SafetyCategory` type. The API will block any contents and responses that fail to meet the thresholds set by these settings. This list overrides the default settings for each `SafetyCategory` specified in the safetySettings. If there is no `SafetySetting` for a given `SafetyCategory` provided in the list, the API will use the default safety setting for that category. Harm categories HARM_CATEGORY_HATE_SPEECH, HARM_CATEGORY_SEXUALLY_EXPLICIT, HARM_CATEGORY_DANGEROUS_CONTENT, HARM_CATEGORY_HARASSMENT, HARM_CATEGORY_CIVIC_INTEGRITY are supported. Refer to the [guide](https://ai.google.dev/gemini-api/docs/safety-settings) for detailed information on available safety settings. Also refer to the [Safety guidance](https://ai.google.dev/gemini-api/docs/safety-guidance) to learn how to incorporate safety considerations in your AI applications.
`systemInstruction` `object (`[Content](https://ai.google.dev/api/caching#Content)`)`
Optional. Developer set [system instruction(s)](https://ai.google.dev/gemini-api/docs/system-instructions). Currently, text only.
`generationConfig` `object (`[GenerationConfig](https://ai.google.dev/api/generate-content#v1beta.GenerationConfig)`)`
Optional. Configuration options for model generation and outputs.
`cachedContent` `string`
Optional. The name of the content [cached](https://ai.google.dev/gemini-api/docs/caching) to use as context to serve the prediction. Format: `cachedContents/{cachedContent}`

### Example request

### Text

### Python

    from google import genai

    client = genai.Client()
    response = client.models.generate_content(
        model="gemini-2.0-flash", contents="Write a story about a magic backpack."
    )
    print(response.text)
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/python/text_generation.py#L26-L32

### Node.js

    // Make sure to include the following import:
    // import {GoogleGenAI} from '@google/genai';
    const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });

    const response = await ai.models.generateContent({
      model: "gemini-2.0-flash",
      contents: "Write a story about a magic backpack.",
    });
    console.log(response.text);
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/javascript/text_generation.js#L36-L44

### Go

    ctx := context.Background()
    client, err := genai.NewClient(ctx, &genai.ClientConfig{
    	APIKey:  os.Getenv("GEMINI_API_KEY"),
    	Backend: genai.BackendGeminiAPI,
    })
    if err != nil {
    	log.Fatal(err)
    }
    contents := []*genai.Content{
    	genai.NewContentFromText("Write a story about a magic backpack.", genai.RoleUser),
    }
    response, err := client.Models.GenerateContent(ctx, "gemini-2.0-flash", contents, nil)
    if err != nil {
    	log.Fatal(err)
    }
    printResponse(response)
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/go/text_generation.go#L16-L31

### Shell

    curl "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=$GEMINI_API_KEY" \
        -H 'Content-Type: application/json' \
        -X POST \
        -d '{
          "contents": [{
            "parts":[{"text": "Write a story about a magic backpack."}]
            }]
           }' 2> /dev/null
    https://github.com/google-gemini/deprecated-generative-ai-python/blob/7a7cc5474ddaa0255a4410e05361028a24400abd/samples/rest/text_generation.sh#L21-L29

### Java

    Client client = new Client();

    GenerateContentResponse response =
            client.models.generateContent(
                    "gemini-2.0-flash",
                    "Write a story about a magic backpack.",
                    null);

    System.out.println(response.text());
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/java/src/main/java/com/example/gemini/TextGeneration.java#L34-L42

### Image

### Python

    from google import genai
    import PIL.Image

    client = genai.Client()
    organ = PIL.Image.open(media / "organ.jpg")
    response = client.models.generate_content(
        model="gemini-2.0-flash", contents=["Tell me about this instrument", organ]
    )
    print(response.text)
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/python/text_generation.py#L50-L58

### Node.js

    // Make sure to include the following import:
    // import {GoogleGenAI} from '@google/genai';
    const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });

    const organ = await ai.files.upload({
      file: path.join(media, "organ.jpg"),
    });

    const response = await ai.models.generateContent({
      model: "gemini-2.0-flash",
      contents: [
        createUserContent([
          "Tell me about this instrument",
          createPartFromUri(organ.uri, organ.mimeType)
        ]),
      ],
    });
    console.log(response.text);
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/javascript/text_generation.js#L70-L87

### Go

    ctx := context.Background()
    client, err := genai.NewClient(ctx, &genai.ClientConfig{
    	APIKey:  os.Getenv("GEMINI_API_KEY"),
    	Backend: genai.BackendGeminiAPI,
    })
    if err != nil {
    	log.Fatal(err)
    }

    file, err := client.Files.UploadFromPath(
    	ctx,
    	filepath.Join(getMedia(), "organ.jpg"),
    	&genai.UploadFileConfig{
    		MIMEType : "image/jpeg",
    	},
    )
    if err != nil {
    	log.Fatal(err)
    }
    parts := []*genai.Part{
    	genai.NewPartFromText("Tell me about this instrument"),
    	genai.NewPartFromURI(file.URI, file.MIMEType),
    }
    contents := []*genai.Content{
    	genai.NewContentFromParts(parts, genai.RoleUser),
    }

    response, err := client.Models.GenerateContent(ctx, "gemini-2.0-flash", contents, nil)
    if err != nil {
    	log.Fatal(err)
    }
    printResponse(response)
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/go/text_generation.go#L66-L97

### Shell

    # Use a temporary file to hold the base64 encoded image data
    TEMP_B64=$(mktemp)
    trap 'rm -f "$TEMP_B64"' EXIT
    base64 $B64FLAGS $IMG_PATH > "$TEMP_B64"

    # Use a temporary file to hold the JSON payload
    TEMP_JSON=$(mktemp)
    trap 'rm -f "$TEMP_JSON"' EXIT

    cat > "$TEMP_JSON" << EOF
    {
      "contents": [{
        "parts":[
          {"text": "Tell me about this instrument"},
          {
            "inline_data": {
              "mime_type":"image/jpeg",
              "data": "$(cat "$TEMP_B64")"
            }
          }
        ]
      }]
    }
    EOF

    curl "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=$GEMINI_API_KEY" \
        -H 'Content-Type: application/json' \
        -X POST \
        -d "@$TEMP_JSON" 2> /dev/null
    https://github.com/google-gemini/deprecated-generative-ai-python/blob/7a7cc5474ddaa0255a4410e05361028a24400abd/samples/rest/text_generation.sh#L41-L70

### Java

    Client client = new Client();

    String path = media_path + "organ.jpg";
    byte[] imageData = Files.readAllBytes(Paths.get(path));

    Content content =
            Content.fromParts(
                    Part.fromText("Tell me about this instrument."),
                    Part.fromBytes(imageData, "image/jpeg"));

    GenerateContentResponse response = client.models.generateContent("gemini-2.0-flash", content, null);

    System.out.println(response.text());
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/java/src/main/java/com/example/gemini/TextGeneration.java#L70-L82

### Audio

### Python

    from google import genai

    client = genai.Client()
    sample_audio = client.files.upload(file=media / "sample.mp3")
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=["Give me a summary of this audio file.", sample_audio],
    )
    print(response.text)
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/python/text_generation.py#L118-L126

### Node.js

    // Make sure to include the following import:
    // import {GoogleGenAI} from '@google/genai';
    const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });

    const audio = await ai.files.upload({
      file: path.join(media, "sample.mp3"),
    });

    const response = await ai.models.generateContent({
      model: "gemini-2.0-flash",
      contents: [
        createUserContent([
          "Give me a summary of this audio file.",
          createPartFromUri(audio.uri, audio.mimeType),
        ]),
      ],
    });
    console.log(response.text);
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/javascript/text_generation.js#L185-L202

### Go

    ctx := context.Background()
    client, err := genai.NewClient(ctx, &genai.ClientConfig{
    	APIKey:  os.Getenv("GEMINI_API_KEY"),
    	Backend: genai.BackendGeminiAPI,
    })
    if err != nil {
    	log.Fatal(err)
    }

    file, err := client.Files.UploadFromPath(
    	ctx,
    	filepath.Join(getMedia(), "sample.mp3"),
    	&genai.UploadFileConfig{
    		MIMEType : "audio/mpeg",
    	},
    )
    if err != nil {
    	log.Fatal(err)
    }

    parts := []*genai.Part{
    	genai.NewPartFromText("Give me a summary of this audio file."),
    	genai.NewPartFromURI(file.URI, file.MIMEType),
    }

    contents := []*genai.Content{
    	genai.NewContentFromParts(parts, genai.RoleUser),
    }

    response, err := client.Models.GenerateContent(ctx, "gemini-2.0-flash", contents, nil)
    if err != nil {
    	log.Fatal(err)
    }
    printResponse(response)
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/go/text_generation.go#L256-L289

### Shell

    # Use File API to upload audio data to API request.
    MIME_TYPE=$(file -b --mime-type "${AUDIO_PATH}")
    NUM_BYTES=$(wc -c < "${AUDIO_PATH}")
    DISPLAY_NAME=AUDIO

    tmp_header_file=upload-header.tmp

    # Initial resumable request defining metadata.
    # The upload url is in the response headers dump them to a file.
    curl "${BASE_URL}/upload/v1beta/files?key=${GEMINI_API_KEY}" \
      -D upload-header.tmp \
      -H "X-Goog-Upload-Protocol: resumable" \
      -H "X-Goog-Upload-Command: start" \
      -H "X-Goog-Upload-Header-Content-Length: ${NUM_BYTES}" \
      -H "X-Goog-Upload-Header-Content-Type: ${MIME_TYPE}" \
      -H "Content-Type: application/json" \
      -d "{'file': {'display_name': '${DISPLAY_NAME}'}}" 2> /dev/null

    upload_url=$(grep -i "x-goog-upload-url: " "${tmp_header_file}" | cut -d" " -f2 | tr -d "\r")
    rm "${tmp_header_file}"

    # Upload the actual bytes.
    curl "${upload_url}" \
      -H "Content-Length: ${NUM_BYTES}" \
      -H "X-Goog-Upload-Offset: 0" \
      -H "X-Goog-Upload-Command: upload, finalize" \
      --data-binary "@${AUDIO_PATH}" 2> /dev/null > file_info.json

    file_uri=$(jq ".file.uri" file_info.json)
    echo file_uri=$file_uri

    curl "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=$GEMINI_API_KEY" \
        -H 'Content-Type: application/json' \
        -X POST \
        -d '{
          "contents": [{
            "parts":[
              {"text": "Please describe this file."},
              {"file_data":{"mime_type": "audio/mpeg", "file_uri": '$file_uri'}}]
            }]
           }' 2> /dev/null > response.json

    cat response.json
    echo

    jq ".candidates[].content.parts[].text" response.json
    https://github.com/google-gemini/deprecated-generative-ai-python/blob/7a7cc5474ddaa0255a4410e05361028a24400abd/samples/rest/text_generation.sh#L174-L220

### Video

### Python

    from google import genai
    import time

    client = genai.Client()
    # Video clip (CC BY 3.0) from https://peach.blender.org/download/
    myfile = client.files.upload(file=media / "Big_Buck_Bunny.mp4")
    print(f"{myfile=}")

    # Poll until the video file is completely processed (state becomes ACTIVE).
    while not myfile.state or myfile.state.name != "ACTIVE":
        print("Processing video...")
        print("File state:", myfile.state)
        time.sleep(5)
        myfile = client.files.get(name=myfile.name)

    response = client.models.generate_content(
        model="gemini-2.0-flash", contents=[myfile, "Describe this video clip"]
    )
    print(f"{response.text=}")
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/python/text_generation.py#L146-L164

### Node.js

    // Make sure to include the following import:
    // import {GoogleGenAI} from '@google/genai';
    const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });

    let video = await ai.files.upload({
      file: path.join(media, 'Big_Buck_Bunny.mp4'),
    });

    // Poll until the video file is completely processed (state becomes ACTIVE).
    while (!video.state || video.state.toString() !== 'ACTIVE') {
      console.log('Processing video...');
      console.log('File state: ', video.state);
      await sleep(5000);
      video = await ai.files.get({name: video.name});
    }

    const response = await ai.models.generateContent({
      model: "gemini-2.0-flash",
      contents: [
        createUserContent([
          "Describe this video clip",
          createPartFromUri(video.uri, video.mimeType),
        ]),
      ],
    });
    console.log(response.text);
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/javascript/text_generation.js#L237-L262

### Go

    ctx := context.Background()
    client, err := genai.NewClient(ctx, &genai.ClientConfig{
    	APIKey:  os.Getenv("GEMINI_API_KEY"),
    	Backend: genai.BackendGeminiAPI,
    })
    if err != nil {
    	log.Fatal(err)
    }

    file, err := client.Files.UploadFromPath(
    	ctx,
    	filepath.Join(getMedia(), "Big_Buck_Bunny.mp4"),
    	&genai.UploadFileConfig{
    		MIMEType : "video/mp4",
    	},
    )
    if err != nil {
    	log.Fatal(err)
    }

    // Poll until the video file is completely processed (state becomes ACTIVE).
    for file.State == genai.FileStateUnspecified || file.State != genai.FileStateActive {
    	fmt.Println("Processing video...")
    	fmt.Println("File state:", file.State)
    	time.Sleep(5 * time.Second)

    	file, err = client.Files.Get(ctx, file.Name, nil)
    	if err != nil {
    		log.Fatal(err)
    	}
    }

    parts := []*genai.Part{
    	genai.NewPartFromText("Describe this video clip"),
    	genai.NewPartFromURI(file.URI, file.MIMEType),
    }

    contents := []*genai.Content{
    	genai.NewContentFromParts(parts, genai.RoleUser),
    }

    response, err := client.Models.GenerateContent(ctx, "gemini-2.0-flash", contents, nil)
    if err != nil {
    	log.Fatal(err)
    }
    printResponse(response)
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/go/text_generation.go#L342-L387

### Shell

    # Use File API to upload audio data to API request.
    MIME_TYPE=$(file -b --mime-type "${VIDEO_PATH}")
    NUM_BYTES=$(wc -c < "${VIDEO_PATH}")
    DISPLAY_NAME=VIDEO

    # Initial resumable request defining metadata.
    # The upload url is in the response headers dump them to a file.
    curl "${BASE_URL}/upload/v1beta/files?key=${GEMINI_API_KEY}" \
      -D "${tmp_header_file}" \
      -H "X-Goog-Upload-Protocol: resumable" \
      -H "X-Goog-Upload-Command: start" \
      -H "X-Goog-Upload-Header-Content-Length: ${NUM_BYTES}" \
      -H "X-Goog-Upload-Header-Content-Type: ${MIME_TYPE}" \
      -H "Content-Type: application/json" \
      -d "{'file': {'display_name': '${DISPLAY_NAME}'}}" 2> /dev/null

    upload_url=$(grep -i "x-goog-upload-url: " "${tmp_header_file}" | cut -d" " -f2 | tr -d "\r")
    rm "${tmp_header_file}"

    # Upload the actual bytes.
    curl "${upload_url}" \
      -H "Content-Length: ${NUM_BYTES}" \
      -H "X-Goog-Upload-Offset: 0" \
      -H "X-Goog-Upload-Command: upload, finalize" \
      --data-binary "@${VIDEO_PATH}" 2> /dev/null > file_info.json

    file_uri=$(jq ".file.uri" file_info.json)
    echo file_uri=$file_uri

    state=$(jq ".file.state" file_info.json)
    echo state=$state

    name=$(jq ".file.name" file_info.json)
    echo name=$name

    while [[ "($state)" = *"PROCESSING"* ]];
    do
      echo "Processing video..."
      sleep 5
      # Get the file of interest to check state
      curl https://generativelanguage.googleapis.com/v1beta/files/$name > file_info.json
      state=$(jq ".file.state" file_info.json)
    done

    curl "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=$GEMINI_API_KEY" \
        -H 'Content-Type: application/json' \
        -X POST \
        -d '{
          "contents": [{
            "parts":[
              {"text": "Transcribe the audio from this video, giving timestamps for salient events in the video. Also provide visual descriptions."},
              {"file_data":{"mime_type": "video/mp4", "file_uri": '$file_uri'}}]
            }]
           }' 2> /dev/null > response.json

    cat response.json
    echo

    jq ".candidates[].content.parts[].text" response.json
    https://github.com/google-gemini/deprecated-generative-ai-python/blob/7a7cc5474ddaa0255a4410e05361028a24400abd/samples/rest/text_generation.sh#L272-L331

### PDF

### Python

    from google import genai

    client = genai.Client()
    sample_pdf = client.files.upload(file=media / "test.pdf")
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=["Give me a summary of this document:", sample_pdf],
    )
    print(f"{response.text=}")
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/python/text_generation.py#L194-L202

### Go

    ctx := context.Background()
    client, err := genai.NewClient(ctx, &genai.ClientConfig{
    	APIKey:  os.Getenv("GEMINI_API_KEY"),
    	Backend: genai.BackendGeminiAPI,
    })
    if err != nil {
    	log.Fatal(err)
    }

    file, err := client.Files.UploadFromPath(
    	ctx,
    	filepath.Join(getMedia(), "test.pdf"),
    	&genai.UploadFileConfig{
    		MIMEType : "application/pdf",
    	},
    )
    if err != nil {
    	log.Fatal(err)
    }

    parts := []*genai.Part{
    	genai.NewPartFromText("Give me a summary of this document:"),
    	genai.NewPartFromURI(file.URI, file.MIMEType),
    }

    contents := []*genai.Content{
    	genai.NewContentFromParts(parts, genai.RoleUser),
    }

    response, err := client.Models.GenerateContent(ctx, "gemini-2.0-flash", contents, nil)
    if err != nil {
    	log.Fatal(err)
    }
    printResponse(response)
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/go/text_generation.go#L452-L485

### Shell

    MIME_TYPE=$(file -b --mime-type "${PDF_PATH}")
    NUM_BYTES=$(wc -c < "${PDF_PATH}")
    DISPLAY_NAME=TEXT


    echo $MIME_TYPE
    tmp_header_file=upload-header.tmp

    # Initial resumable request defining metadata.
    # The upload url is in the response headers dump them to a file.
    curl "${BASE_URL}/upload/v1beta/files?key=${GEMINI_API_KEY}" \
      -D upload-header.tmp \
      -H "X-Goog-Upload-Protocol: resumable" \
      -H "X-Goog-Upload-Command: start" \
      -H "X-Goog-Upload-Header-Content-Length: ${NUM_BYTES}" \
      -H "X-Goog-Upload-Header-Content-Type: ${MIME_TYPE}" \
      -H "Content-Type: application/json" \
      -d "{'file': {'display_name': '${DISPLAY_NAME}'}}" 2> /dev/null

    upload_url=$(grep -i "x-goog-upload-url: " "${tmp_header_file}" | cut -d" " -f2 | tr -d "\r")
    rm "${tmp_header_file}"

    # Upload the actual bytes.
    curl "${upload_url}" \
      -H "Content-Length: ${NUM_BYTES}" \
      -H "X-Goog-Upload-Offset: 0" \
      -H "X-Goog-Upload-Command: upload, finalize" \
      --data-binary "@${PDF_PATH}" 2> /dev/null > file_info.json

    file_uri=$(jq ".file.uri" file_info.json)
    echo file_uri=$file_uri

    # Now generate content using that file
    curl "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=$GEMINI_API_KEY" \
        -H 'Content-Type: application/json' \
        -X POST \
        -d '{
          "contents": [{
            "parts":[
              {"text": "Can you add a few more lines to this poem?"},
              {"file_data":{"mime_type": "application/pdf", "file_uri": '$file_uri'}}]
            }]
           }' 2> /dev/null > response.json

    cat response.json
    echo

    jq ".candidates[].content.parts[].text" response.json
    https://github.com/google-gemini/deprecated-generative-ai-python/blob/7a7cc5474ddaa0255a4410e05361028a24400abd/samples/rest/text_generation.sh#L393-L441

### Chat

### Python

    from google import genai
    from google.genai import types

    client = genai.Client()
    # Pass initial history using the "history" argument
    chat = client.chats.create(
        model="gemini-2.0-flash",
        history=[
            types.Content(role="user", parts=[types.Part(text="Hello")]),
            types.Content(
                role="model",
                parts=[
                    types.Part(
                        text="Great to meet you. What would you like to know?"
                    )
                ],
            ),
        ],
    )
    response = chat.send_message(message="I have 2 dogs in my house.")
    print(response.text)
    response = chat.send_message(message="How many paws are in my house?")
    print(response.text)
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/python/chat.py#L25-L47

### Node.js

    // Make sure to include the following import:
    // import {GoogleGenAI} from '@google/genai';
    const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });
    const chat = ai.chats.create({
      model: "gemini-2.0-flash",
      history: [
        {
          role: "user",
          parts: [{ text: "Hello" }],
        },
        {
          role: "model",
          parts: [{ text: "Great to meet you. What would you like to know?" }],
        },
      ],
    });

    const response1 = await chat.sendMessage({
      message: "I have 2 dogs in my house.",
    });
    console.log("Chat response 1:", response1.text);

    const response2 = await chat.sendMessage({
      message: "How many paws are in my house?",
    });
    console.log("Chat response 2:", response2.text);
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/javascript/chat.js#L33-L58

### Go

    ctx := context.Background()
    client, err := genai.NewClient(ctx, &genai.ClientConfig{
    	APIKey:  os.Getenv("GEMINI_API_KEY"),
    	Backend: genai.BackendGeminiAPI,
    })
    if err != nil {
    	log.Fatal(err)
    }

    // Pass initial history using the History field.
    history := []*genai.Content{
    	genai.NewContentFromText("Hello", genai.RoleUser),
    	genai.NewContentFromText("Great to meet you. What would you like to know?", genai.RoleModel),
    }

    chat, err := client.Chats.Create(ctx, "gemini-2.0-flash", nil, history)
    if err != nil {
    	log.Fatal(err)
    }

    firstResp, err := chat.SendMessage(ctx, genai.Part{Text: "I have 2 dogs in my house."})
    if err != nil {
    	log.Fatal(err)
    }
    fmt.Println(firstResp.Text())

    secondResp, err := chat.SendMessage(ctx, genai.Part{Text: "How many paws are in my house?"})
    if err != nil {
    	log.Fatal(err)
    }
    fmt.Println(secondResp.Text())
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/go/chat.go#L16-L46

### Shell

    curl https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=$GEMINI_API_KEY \
        -H 'Content-Type: application/json' \
        -X POST \
        -d '{
          "contents": [
            {"role":"user",
             "parts":[{
               "text": "Hello"}]},
            {"role": "model",
             "parts":[{
               "text": "Great to meet you. What would you like to know?"}]},
            {"role":"user",
             "parts":[{
               "text": "I have two dogs in my house. How many paws are in my house?"}]},
          ]
        }' 2> /dev/null | grep "text"
    https://github.com/google-gemini/deprecated-generative-ai-python/blob/7a7cc5474ddaa0255a4410e05361028a24400abd/samples/rest/chat.sh#L7-L23

### Java

    Client client = new Client();

    Content userContent = Content.fromParts(Part.fromText("Hello"));
    Content modelContent =
            Content.builder()
                    .role("model")
                    .parts(
                            Collections.singletonList(
                                    Part.fromText("Great to meet you. What would you like to know?")
                            )
                    ).build();

    Chat chat = client.chats.create(
            "gemini-2.0-flash",
            GenerateContentConfig.builder()
                    .systemInstruction(userContent)
                    .systemInstruction(modelContent)
                    .build()
    );

    GenerateContentResponse response1 = chat.sendMessage("I have 2 dogs in my house.");
    System.out.println(response1.text());

    GenerateContentResponse response2 = chat.sendMessage("How many paws are in my house?");
    System.out.println(response2.text());
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/java/src/main/java/com/example/gemini/ChatSession.java#L32-L57

### Cache

### Python

    from google import genai
    from google.genai import types

    client = genai.Client()
    document = client.files.upload(file=media / "a11.txt")
    model_name = "gemini-1.5-flash-001"

    cache = client.caches.create(
        model=model_name,
        config=types.CreateCachedContentConfig(
            contents=[document],
            system_instruction="You are an expert analyzing transcripts.",
        ),
    )
    print(cache)

    response = client.models.generate_content(
        model=model_name,
        contents="Please summarize this transcript",
        config=types.GenerateContentConfig(cached_content=cache.name),
    )
    print(response.text)
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/python/cache.py#L25-L46

### Node.js

    // Make sure to include the following import:
    // import {GoogleGenAI} from '@google/genai';
    const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });
    const filePath = path.join(media, "a11.txt");
    const document = await ai.files.upload({
      file: filePath,
      config: { mimeType: "text/plain" },
    });
    console.log("Uploaded file name:", document.name);
    const modelName = "gemini-1.5-flash-001";

    const contents = [
      createUserContent(createPartFromUri(document.uri, document.mimeType)),
    ];

    const cache = await ai.caches.create({
      model: modelName,
      config: {
        contents: contents,
        systemInstruction: "You are an expert analyzing transcripts.",
      },
    });
    console.log("Cache created:", cache);

    const response = await ai.models.generateContent({
      model: modelName,
      contents: "Please summarize this transcript",
      config: { cachedContent: cache.name },
    });
    console.log("Response text:", response.text);
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/javascript/cache.js#L33-L62

### Go

    ctx := context.Background()
    client, err := genai.NewClient(ctx, &genai.ClientConfig{
    	APIKey:  os.Getenv("GEMINI_API_KEY"),
    	Backend: genai.BackendGeminiAPI,
    })
    if err != nil {
    	log.Fatal(err)
    }

    modelName := "gemini-1.5-flash-001"
    document, err := client.Files.UploadFromPath(
    	ctx,
    	filepath.Join(getMedia(), "a11.txt"),
    	&genai.UploadFileConfig{
    		MIMEType : "text/plain",
    	},
    )
    if err != nil {
    	log.Fatal(err)
    }
    parts := []*genai.Part{
    	genai.NewPartFromURI(document.URI, document.MIMEType),
    }
    contents := []*genai.Content{
    	genai.NewContentFromParts(parts, genai.RoleUser),
    }
    cache, err := client.Caches.Create(ctx, modelName, &genai.CreateCachedContentConfig{
    	Contents: contents,
    	SystemInstruction: genai.NewContentFromText(
    		"You are an expert analyzing transcripts.", genai.RoleUser,
    	),
    })
    if err != nil {
    	log.Fatal(err)
    }
    fmt.Println("Cache created:")
    fmt.Println(cache)

    // Use the cache for generating content.
    response, err := client.Models.GenerateContent(
    	ctx,
    	modelName,
    	genai.Text("Please summarize this transcript"),
    	&genai.GenerateContentConfig{
    		CachedContent: cache.Name,
    	},
    )
    if err != nil {
    	log.Fatal(err)
    }
    printResponse(response)
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/go/cache.go#L16-L66

### Tuned Model

### Python

    # With Gemini 2 we're launching a new SDK. See the following doc for details.
    # https://ai.google.dev/gemini-api/docs/migrate
    https://github.com/google-gemini/deprecated-generative-ai-python/blob/7a7cc5474ddaa0255a4410e05361028a24400abd/README.md#L23-L24

### JSON Mode

### Python

    from google import genai
    from google.genai import types
    from typing_extensions import TypedDict

    class Recipe(TypedDict):
        recipe_name: str
        ingredients: list[str]

    client = genai.Client()
    result = client.models.generate_content(
        model="gemini-2.0-flash",
        contents="List a few popular cookie recipes.",
        config=types.GenerateContentConfig(
            response_mime_type="application/json", response_schema=list[Recipe]
        ),
    )
    print(result)
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/python/controlled_generation.py#L25-L41

### Node.js

    // Make sure to include the following import:
    // import {GoogleGenAI} from '@google/genai';
    const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });
    const response = await ai.models.generateContent({
      model: "gemini-2.0-flash",
      contents: "List a few popular cookie recipes.",
      config: {
        responseMimeType: "application/json",
        responseSchema: {
          type: "array",
          items: {
            type: "object",
            properties: {
              recipeName: { type: "string" },
              ingredients: { type: "array", items: { type: "string" } },
            },
            required: ["recipeName", "ingredients"],
          },
        },
      },
    });
    console.log(response.text);
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/javascript/controlled_generation.js#L33-L54

### Go

    ctx := context.Background()
    client, err := genai.NewClient(ctx, &genai.ClientConfig{
    	APIKey:  os.Getenv("GEMINI_API_KEY"),
    	Backend: genai.BackendGeminiAPI,
    })
    if err != nil {
    	log.Fatal(err)
    }

    schema := &genai.Schema{
    	Type: genai.TypeArray,
    	Items: &genai.Schema{
    		Type: genai.TypeObject,
    		Properties: map[string]*genai.Schema{
    			"recipe_name": {Type: genai.TypeString},
    			"ingredients": {
    				Type:  genai.TypeArray,
    				Items: &genai.Schema{Type: genai.TypeString},
    			},
    		},
    		Required: []string{"recipe_name"},
    	},
    }

    config := &genai.GenerateContentConfig{
    	ResponseMIMEType: "application/json",
    	ResponseSchema:   schema,
    }

    response, err := client.Models.GenerateContent(
    	ctx,
    	"gemini-2.0-flash",
    	genai.Text("List a few popular cookie recipes."),
    	config,
    )
    if err != nil {
    	log.Fatal(err)
    }
    printResponse(response)
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/go/controlled_generation.go#L14-L52

### Shell

    curl "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=$GEMINI_API_KEY" \
    -H 'Content-Type: application/json' \
    -d '{
        "contents": [{
          "parts":[
            {"text": "List 5 popular cookie recipes"}
            ]
        }],
        "generationConfig": {
            "response_mime_type": "application/json",
            "response_schema": {
              "type": "ARRAY",
              "items": {
                "type": "OBJECT",
                "properties": {
                  "recipe_name": {"type":"STRING"},
                }
              }
            }
        }
    }' 2> /dev/null | head
    https://github.com/google-gemini/deprecated-generative-ai-python/blob/7a7cc5474ddaa0255a4410e05361028a24400abd/samples/rest/controlled_generation.sh#L5-L25

### Java

    Client client = new Client();

    Schema recipeSchema = Schema.builder()
            .type(Array.class.getSimpleName())
            .items(Schema.builder()
                    .type(Object.class.getSimpleName())
                    .properties(
                            Map.of("recipe_name", Schema.builder()
                                            .type(String.class.getSimpleName())
                                            .build(),
                                    "ingredients", Schema.builder()
                                            .type(Array.class.getSimpleName())
                                            .items(Schema.builder()
                                                    .type(String.class.getSimpleName())
                                                    .build())
                                            .build())
                    )
                    .required(List.of("recipe_name", "ingredients"))
                    .build())
            .build();

    GenerateContentConfig config =
            GenerateContentConfig.builder()
                    .responseMimeType("application/json")
                    .responseSchema(recipeSchema)
                    .build();

    GenerateContentResponse response =
            client.models.generateContent(
                    "gemini-2.0-flash",
                    "List a few popular cookie recipes.",
                    config);

    System.out.println(response.text());
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/java/src/main/java/com/example/gemini/ControlledGeneration.java#L39-L72

### Code execution

### Python

    from google import genai
    from google.genai import types

    client = genai.Client()
    response = client.models.generate_content(
        model="gemini-2.0-pro-exp-02-05",
        contents=(
            "Write and execute code that calculates the sum of the first 50 prime numbers. "
            "Ensure that only the executable code and its resulting output are generated."
        ),
    )
    # Each part may contain text, executable code, or an execution result.
    for part in response.candidates[0].content.parts:
        print(part, "\n")

    print("-" * 80)
    # The .text accessor concatenates the parts into a markdown-formatted text.
    print("\n", response.text)
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/python/code_execution.py#L22-L39

### Go

    ctx := context.Background()
    client, err := genai.NewClient(ctx, &genai.ClientConfig{
    	APIKey:  os.Getenv("GEMINI_API_KEY"),
    	Backend: genai.BackendGeminiAPI,
    })
    if err != nil {
    	log.Fatal(err)
    }

    response, err := client.Models.GenerateContent(
    	ctx,
    	"gemini-2.0-pro-exp-02-05",
    	genai.Text(
    		`Write and execute code that calculates the sum of the first 50 prime numbers.
    		 Ensure that only the executable code and its resulting output are generated.`,
    	),
    	&genai.GenerateContentConfig{},
    )
    if err != nil {
    	log.Fatal(err)
    }

    // Print the response.
    printResponse(response)

    fmt.Println("---")
    fmt.Println(response.Text())
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/go/code_execution.go#L14-L40

### Java

    Client client = new Client();

    String prompt = """
            Write and execute code that calculates the sum of the first 50 prime numbers.
            Ensure that only the executable code and its resulting output are generated.
            """;

    GenerateContentResponse response =
            client.models.generateContent(
                    "gemini-2.0-pro-exp-02-05",
                    prompt,
                    null);

    for (Part part : response.candidates().get().getFirst().content().get().parts().get()) {
        System.out.println(part + "\n");
    }

    System.out.println("-".repeat(80));
    System.out.println(response.text());
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/java/src/main/java/com/example/gemini/CodeExecution.java#L32-L50

### Function Calling

### Python

    from google import genai
    from google.genai import types

    client = genai.Client()

    def add(a: float, b: float) -> float:
        """returns a + b."""
        return a + b

    def subtract(a: float, b: float) -> float:
        """returns a - b."""
        return a - b

    def multiply(a: float, b: float) -> float:
        """returns a * b."""
        return a * b

    def divide(a: float, b: float) -> float:
        """returns a / b."""
        return a / b

    # Create a chat session; function calling (via tools) is enabled in the config.
    chat = client.chats.create(
        model="gemini-2.0-flash",
        config=types.GenerateContentConfig(tools=[add, subtract, multiply, divide]),
    )
    response = chat.send_message(
        message="I have 57 cats, each owns 44 mittens, how many mittens is that in total?"
    )
    print(response.text)
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/python/function_calling.py#L22-L51

### Go

    ctx := context.Background()
    client, err := genai.NewClient(ctx, &genai.ClientConfig{
    	APIKey:  os.Getenv("GEMINI_API_KEY"),
    	Backend: genai.BackendGeminiAPI,
    })
    if err != nil {
    	log.Fatal(err)
    }
    modelName := "gemini-2.0-flash"

    // Create the function declarations for arithmetic operations.
    addDeclaration := createArithmeticToolDeclaration("addNumbers", "Return the result of adding two numbers.")
    subtractDeclaration := createArithmeticToolDeclaration("subtractNumbers", "Return the result of subtracting the second number from the first.")
    multiplyDeclaration := createArithmeticToolDeclaration("multiplyNumbers", "Return the product of two numbers.")
    divideDeclaration := createArithmeticToolDeclaration("divideNumbers", "Return the quotient of dividing the first number by the second.")

    // Group the function declarations as a tool.
    tools := []*genai.Tool{
    	{
    		FunctionDeclarations: []*genai.FunctionDeclaration{
    			addDeclaration,
    			subtractDeclaration,
    			multiplyDeclaration,
    			divideDeclaration,
    		},
    	},
    }

    // Create the content prompt.
    contents := []*genai.Content{
    	genai.NewContentFromText(
    		"I have 57 cats, each owns 44 mittens, how many mittens is that in total?", genai.RoleUser,
    	),
    }

    // Set up the generate content configuration with function calling enabled.
    config := &genai.GenerateContentConfig{
    	Tools: tools,
    	ToolConfig: &genai.ToolConfig{
    		FunctionCallingConfig: &genai.FunctionCallingConfig{
    			// The mode equivalent to FunctionCallingConfigMode.ANY in JS.
    			Mode: genai.FunctionCallingConfigModeAny,
    		},
    	},
    }

    genContentResp, err := client.Models.GenerateContent(ctx, modelName, contents, config)
    if err != nil {
    	log.Fatal(err)
    }

    // Assume the response includes a list of function calls.
    if len(genContentResp.FunctionCalls()) == 0 {
    	log.Println("No function call returned from the AI.")
    	return nil
    }
    functionCall := genContentResp.FunctionCalls()[0]
    log.Printf("Function call: %+v\n", functionCall)

    // Marshal the Args map into JSON bytes.
    argsMap, err := json.Marshal(functionCall.Args)
    if err != nil {
    	log.Fatal(err)
    }

    // Unmarshal the JSON bytes into the ArithmeticArgs struct.
    var args ArithmeticArgs
    if err := json.Unmarshal(argsMap, &args); err != nil {
    	log.Fatal(err)
    }

    // Map the function name to the actual arithmetic function.
    var result float64
    switch functionCall.Name {
    	case "addNumbers":
    		result = add(args.FirstParam, args.SecondParam)
    	case "subtractNumbers":
    		result = subtract(args.FirstParam, args.SecondParam)
    	case "multiplyNumbers":
    		result = multiply(args.FirstParam, args.SecondParam)
    	case "divideNumbers":
    		result = divide(args.FirstParam, args.SecondParam)
    	default:
    		return fmt.Errorf("unimplemented function: %s", functionCall.Name)
    }
    log.Printf("Function result: %v\n", result)

    // Prepare the final result message as content.
    resultContents := []*genai.Content{
    	genai.NewContentFromText("The final result is " + fmt.Sprintf("%v", result), genai.RoleUser),
    }

    // Use GenerateContent to send the final result.
    finalResponse, err := client.Models.GenerateContent(ctx, modelName, resultContents, &genai.GenerateContentConfig{})
    if err != nil {
    	log.Fatal(err)
    }

    printResponse(finalResponse)
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/go/function_calling.go#L63-L161

### Node.js

      // Make sure to include the following import:
      // import {GoogleGenAI} from '@google/genai';
      const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });

      /**
       * The add function returns the sum of two numbers.
       * @param {number} a
       * @param {number} b
       * @returns {number}
       */
      function add(a, b) {
        return a + b;
      }

      /**
       * The subtract function returns the difference (a - b).
       * @param {number} a
       * @param {number} b
       * @returns {number}
       */
      function subtract(a, b) {
        return a - b;
      }

      /**
       * The multiply function returns the product of two numbers.
       * @param {number} a
       * @param {number} b
       * @returns {number}
       */
      function multiply(a, b) {
        return a * b;
      }

      /**
       * The divide function returns the quotient of a divided by b.
       * @param {number} a
       * @param {number} b
       * @returns {number}
       */
      function divide(a, b) {
        return a / b;
      }

      const addDeclaration = {
        name: "addNumbers",
        parameters: {
          type: "object",
          description: "Return the result of adding two numbers.",
          properties: {
            firstParam: {
              type: "number",
              description:
                "The first parameter which can be an integer or a floating point number.",
            },
            secondParam: {
              type: "number",
              description:
                "The second parameter which can be an integer or a floating point number.",
            },
          },
          required: ["firstParam", "secondParam"],
        },
      };

      const subtractDeclaration = {
        name: "subtractNumbers",
        parameters: {
          type: "object",
          description:
            "Return the result of subtracting the second number from the first.",
          properties: {
            firstParam: {
              type: "number",
              description: "The first parameter.",
            },
            secondParam: {
              type: "number",
              description: "The second parameter.",
            },
          },
          required: ["firstParam", "secondParam"],
        },
      };

      const multiplyDeclaration = {
        name: "multiplyNumbers",
        parameters: {
          type: "object",
          description: "Return the product of two numbers.",
          properties: {
            firstParam: {
              type: "number",
              description: "The first parameter.",
            },
            secondParam: {
              type: "number",
              description: "The second parameter.",
            },
          },
          required: ["firstParam", "secondParam"],
        },
      };

      const divideDeclaration = {
        name: "divideNumbers",
        parameters: {
          type: "object",
          description:
            "Return the quotient of dividing the first number by the second.",
          properties: {
            firstParam: {
              type: "number",
              description: "The first parameter.",
            },
            secondParam: {
              type: "number",
              description: "The second parameter.",
            },
          },
          required: ["firstParam", "secondParam"],
        },
      };

      // Step 1: Call generateContent with function calling enabled.
      const generateContentResponse = await ai.models.generateContent({
        model: "gemini-2.0-flash",
        contents:
          "I have 57 cats, each owns 44 mittens, how many mittens is that in total?",
        config: {
          toolConfig: {
            functionCallingConfig: {
              mode: FunctionCallingConfigMode.ANY,
            },
          },
          tools: [
            {
              functionDeclarations: [
                addDeclaration,
                subtractDeclaration,
                multiplyDeclaration,
                divideDeclaration,
              ],
            },
          ],
        },
      });

      // Step 2: Extract the function call.(
      // Assuming the response contains a 'functionCalls' array.
      const functionCall =
        generateContentResponse.functionCalls &&
        generateContentResponse.functionCalls[0];
      console.log(functionCall);

      // Parse the arguments.
      const args = functionCall.args;
      // Expected args format: { firstParam: number, secondParam: number }

      // Step 3: Invoke the actual function based on the function name.
      const functionMapping = {
        addNumbers: add,
        subtractNumbers: subtract,
        multiplyNumbers: multiply,
        divideNumbers: divide,
      };
      const func = functionMapping[functionCall.name];
      if (!func) {
        console.error("Unimplemented error:", functionCall.name);
        return generateContentResponse;
      }
      const resultValue = func(args.firstParam, args.secondParam);
      console.log("Function result:", resultValue);

      // Step 4: Use the chat API to send the result as the final answer.
      const chat = ai.chats.create({ model: "gemini-2.0-flash" });
      const chatResponse = await chat.sendMessage({
        message: "The final result is " + resultValue,
      });
      console.log(chatResponse.text);
      return chatResponse;
    }
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/javascript/function_calling.js#L22-L-1

### Shell


    cat > tools.json << EOF
    {
      "function_declarations": [
        {
          "name": "enable_lights",
          "description": "Turn on the lighting system."
        },
        {
          "name": "set_light_color",
          "description": "Set the light color. Lights must be enabled for this to work.",
          "parameters": {
            "type": "object",
            "properties": {
              "rgb_hex": {
                "type": "string",
                "description": "The light color as a 6-digit hex string, e.g. ff0000 for red."
              }
            },
            "required": [
              "rgb_hex"
            ]
          }
        },
        {
          "name": "stop_lights",
          "description": "Turn off the lighting system."
        }
      ]
    }
    EOF

    curl "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=$GEMINI_API_KEY" \
      -H 'Content-Type: application/json' \
      -d @<(echo '
      {
        "system_instruction": {
          "parts": {
            "text": "You are a helpful lighting system bot. You can turn lights on and off, and you can set the color. Do not perform any other tasks."
          }
        },
        "tools": ['$(cat tools.json)'],

        "tool_config": {
          "function_calling_config": {"mode": "auto"}
        },

        "contents": {
          "role": "user",
          "parts": {
            "text": "Turn on the lights please."
          }
        }
      }
    ') 2>/dev/null |sed -n '/"content"/,/"finishReason"/p'
    https://github.com/google-gemini/deprecated-generative-ai-python/blob/7a7cc5474ddaa0255a4410e05361028a24400abd/samples/rest/function_calling.sh#L4-L59

### Java

    Client client = new Client();

    FunctionDeclaration addFunction =
            FunctionDeclaration.builder()
                    .name("addNumbers")
                    .parameters(
                            Schema.builder()
                                    .type("object")
                                    .properties(Map.of(
                                            "firstParam", Schema.builder().type("number").description("First number").build(),
                                            "secondParam", Schema.builder().type("number").description("Second number").build()))
                                    .required(Arrays.asList("firstParam", "secondParam"))
                                    .build())
                    .build();

    FunctionDeclaration subtractFunction =
            FunctionDeclaration.builder()
                    .name("subtractNumbers")
                    .parameters(
                            Schema.builder()
                                    .type("object")
                                    .properties(Map.of(
                                            "firstParam", Schema.builder().type("number").description("First number").build(),
                                            "secondParam", Schema.builder().type("number").description("Second number").build()))
                                    .required(Arrays.asList("firstParam", "secondParam"))
                                    .build())
                    .build();

    FunctionDeclaration multiplyFunction =
            FunctionDeclaration.builder()
                    .name("multiplyNumbers")
                    .parameters(
                            Schema.builder()
                                    .type("object")
                                    .properties(Map.of(
                                            "firstParam", Schema.builder().type("number").description("First number").build(),
                                            "secondParam", Schema.builder().type("number").description("Second number").build()))
                                    .required(Arrays.asList("firstParam", "secondParam"))
                                    .build())
                    .build();

    FunctionDeclaration divideFunction =
            FunctionDeclaration.builder()
                    .name("divideNumbers")
                    .parameters(
                            Schema.builder()
                                    .type("object")
                                    .properties(Map.of(
                                            "firstParam", Schema.builder().type("number").description("First number").build(),
                                            "secondParam", Schema.builder().type("number").description("Second number").build()))
                                    .required(Arrays.asList("firstParam", "secondParam"))
                                    .build())
                    .build();

    GenerateContentConfig config = GenerateContentConfig.builder()
            .toolConfig(ToolConfig.builder().functionCallingConfig(
                    FunctionCallingConfig.builder().mode("ANY").build()
            ).build())
            .tools(
                    Collections.singletonList(
                            Tool.builder().functionDeclarations(
                                    Arrays.asList(
                                            addFunction,
                                            subtractFunction,
                                            divideFunction,
                                            multiplyFunction
                                    )
                            ).build()

                    )
            )
            .build();

    GenerateContentResponse response =
            client.models.generateContent(
                    "gemini-2.0-flash",
                    "I have 57 cats, each owns 44 mittens, how many mittens is that in total?",
                    config);


    if (response.functionCalls() == null || response.functionCalls().isEmpty()) {
        System.err.println("No function call received");
        return null;
    }

    var functionCall = response.functionCalls().getFirst();
    String functionName = functionCall.name().get();
    var arguments = functionCall.args();

    Map<String, BiFunction<Double, Double, Double>> functionMapping = new HashMap<>();
    functionMapping.put("addNumbers", (a, b) -> a + b);
    functionMapping.put("subtractNumbers", (a, b) -> a - b);
    functionMapping.put("multiplyNumbers", (a, b) -> a * b);
    functionMapping.put("divideNumbers", (a, b) -> b != 0 ? a / b : Double.NaN);

    BiFunction<Double, Double, Double> function = functionMapping.get(functionName);

    Number firstParam = (Number) arguments.get().get("firstParam");
    Number secondParam = (Number) arguments.get().get("secondParam");
    Double result = function.apply(firstParam.doubleValue(), secondParam.doubleValue());

    System.out.println(result);
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/java/src/main/java/com/example/gemini/FunctionCalling.java#L38-L139

### Generation config

### Python

    from google import genai
    from google.genai import types

    client = genai.Client()
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents="Tell me a story about a magic backpack.",
        config=types.GenerateContentConfig(
            candidate_count=1,
            stop_sequences=["x"],
            max_output_tokens=20,
            temperature=1.0,
        ),
    )
    print(response.text)
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/python/configure_model_parameters.py#L22-L36

### Node.js

    // Make sure to include the following import:
    // import {GoogleGenAI} from '@google/genai';
    const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });

    const response = await ai.models.generateContent({
      model: "gemini-2.0-flash",
      contents: "Tell me a story about a magic backpack.",
      config: {
        candidateCount: 1,
        stopSequences: ["x"],
        maxOutputTokens: 20,
        temperature: 1.0,
      },
    });

    console.log(response.text);
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/javascript/configure_model_parameters.js#L22-L37

### Go

    ctx := context.Background()
    client, err := genai.NewClient(ctx, &genai.ClientConfig{
    	APIKey:  os.Getenv("GEMINI_API_KEY"),
    	Backend: genai.BackendGeminiAPI,
    })
    if err != nil {
    	log.Fatal(err)
    }

    // Create local variables for parameters.
    candidateCount := int32(1)
    maxOutputTokens := int32(20)
    temperature := float32(1.0)

    response, err := client.Models.GenerateContent(
    	ctx,
    	"gemini-2.0-flash",
    	genai.Text("Tell me a story about a magic backpack."),
    	&genai.GenerateContentConfig{
    		CandidateCount:  candidateCount,
    		StopSequences:   []string{"x"},
    		MaxOutputTokens: maxOutputTokens,
    		Temperature:     &temperature,
    	},
    )
    if err != nil {
    	log.Fatal(err)
    }

    printResponse(response)
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/go/configure_model_parameters.go#L13-L42

### Shell

    curl https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=$GEMINI_API_KEY \
        -H 'Content-Type: application/json' \
        -X POST \
        -d '{
            "contents": [{
                "parts":[
                    {"text": "Explain how AI works"}
                ]
            }],
            "generationConfig": {
                "stopSequences": [
                    "Title"
                ],
                "temperature": 1.0,
                "maxOutputTokens": 800,
                "topP": 0.8,
                "topK": 10
            }
        }'  2> /dev/null | grep "text"
    https://github.com/google-gemini/deprecated-generative-ai-python/blob/7a7cc5474ddaa0255a4410e05361028a24400abd/samples/rest/configure_model_parameters.sh#L4-L23

### Java

    Client client = new Client();

    GenerateContentConfig config =
            GenerateContentConfig.builder()
                    .candidateCount(1)
                    .stopSequences(List.of("x"))
                    .maxOutputTokens(20)
                    .temperature(1.0F)
                    .build();

    GenerateContentResponse response =
            client.models.generateContent(
                    "gemini-2.0-flash",
                    "Tell me a story about a magic backpack.",
                    config);

    System.out.println(response.text());
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/java/src/main/java/com/example/gemini/ConfigureModelParameters.java#L29-L45

### Safety Settings

### Python

    from google import genai
    from google.genai import types

    client = genai.Client()
    unsafe_prompt = (
        "I support Martians Soccer Club and I think Jupiterians Football Club sucks! "
        "Write a ironic phrase about them including expletives."
    )
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=unsafe_prompt,
        config=types.GenerateContentConfig(
            safety_settings=[
                types.SafetySetting(
                    category="HARM_CATEGORY_HATE_SPEECH",
                    threshold="BLOCK_MEDIUM_AND_ABOVE",
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_ONLY_HIGH"
                ),
            ]
        ),
    )
    try:
        print(response.text)
    except Exception:
        print("No information generated by the model.")

    print(response.candidates[0].safety_ratings)
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/python/safety_settings.py#L48-L76

### Node.js

      // Make sure to include the following import:
      // import {GoogleGenAI} from '@google/genai';
      const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });
      const unsafePrompt =
        "I support Martians Soccer Club and I think Jupiterians Football Club sucks! Write a ironic phrase about them including expletives.";

      const response = await ai.models.generateContent({
        model: "gemini-2.0-flash",
        contents: unsafePrompt,
        config: {
          safetySettings: [
            {
              category: "HARM_CATEGORY_HATE_SPEECH",
              threshold: "BLOCK_MEDIUM_AND_ABOVE",
            },
            {
              category: "HARM_CATEGORY_HARASSMENT",
              threshold: "BLOCK_ONLY_HIGH",
            },
          ],
        },
      });

      try {
        console.log("Generated text:", response.text);
      } catch (error) {
        console.log("No information generated by the model.");
      }
      console.log("Safety ratings:", response.candidates[0].safetyRatings);
      return response;
    }
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/javascript/safety_settings.js#L49-L-1

### Go

    ctx := context.Background()
    client, err := genai.NewClient(ctx, &genai.ClientConfig{
    	APIKey:  os.Getenv("GEMINI_API_KEY"),
    	Backend: genai.BackendGeminiAPI,
    })
    if err != nil {
    	log.Fatal(err)
    }

    unsafePrompt := "I support Martians Soccer Club and I think Jupiterians Football Club sucks! " +
    	"Write a ironic phrase about them including expletives."

    config := &genai.GenerateContentConfig{
    	SafetySettings: []*genai.SafetySetting{
    		{
    			Category:  "HARM_CATEGORY_HATE_SPEECH",
    			Threshold: "BLOCK_MEDIUM_AND_ABOVE",
    		},
    		{
    			Category:  "HARM_CATEGORY_HARASSMENT",
    			Threshold: "BLOCK_ONLY_HIGH",
    		},
    	},
    }
    contents := []*genai.Content{
    	genai.NewContentFromText(unsafePrompt, genai.RoleUser),
    }
    response, err := client.Models.GenerateContent(ctx, "gemini-2.0-flash", contents, config)
    if err != nil {
    	log.Fatal(err)
    }

    // Print the generated text.
    text := response.Text()
    fmt.Println("Generated text:", text)

    // Print the and safety ratings from the first candidate.
    if len(response.Candidates) > 0 {
    	fmt.Println("Finish reason:", response.Candidates[0].FinishReason)
    	safetyRatings, err := json.MarshalIndent(response.Candidates[0].SafetyRatings, "", "  ")
    	if err != nil {
    		return err
    	}
    	fmt.Println("Safety ratings:", string(safetyRatings))
    } else {
    	fmt.Println("No candidate returned.")
    }
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/go/safety_settings.go#L60-L106

### Shell

    echo '{
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"}
        ],
        "contents": [{
            "parts":[{
                "text": "'I support Martians Soccer Club and I think Jupiterians Football Club sucks! Write a ironic phrase about them.'"}]}]}' > request.json

    curl "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=$GEMINI_API_KEY" \
        -H 'Content-Type: application/json' \
        -X POST \
        -d @request.json 2> /dev/null
    https://github.com/google-gemini/deprecated-generative-ai-python/blob/7a7cc5474ddaa0255a4410e05361028a24400abd/samples/rest/safety_settings.sh#L20-L33

### Java

    Client client = new Client();

    String unsafePrompt = """
             I support Martians Soccer Club and I think Jupiterians Football Club sucks!
             Write a ironic phrase about them including expletives.
            """;

    GenerateContentConfig config =
            GenerateContentConfig.builder()
                    .safetySettings(Arrays.asList(
                            SafetySetting.builder()
                                    .category("HARM_CATEGORY_HATE_SPEECH")
                                    .threshold("BLOCK_MEDIUM_AND_ABOVE")
                                    .build(),
                            SafetySetting.builder()
                                    .category("HARM_CATEGORY_HARASSMENT")
                                    .threshold("BLOCK_ONLY_HIGH")
                                    .build()
                    )).build();

    GenerateContentResponse response =
            client.models.generateContent(
                    "gemini-2.0-flash",
                    unsafePrompt,
                    config);

    try {
        System.out.println(response.text());
    } catch (Exception e) {
        System.out.println("No information generated by the model");
    }

    System.out.println(response.candidates().get().getFirst().safetyRatings());
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/java/src/main/java/com/example/gemini/SafetySettings.java#L60-L92

### System Instruction

### Python

    from google import genai
    from google.genai import types

    client = genai.Client()
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents="Good morning! How are you?",
        config=types.GenerateContentConfig(
            system_instruction="You are a cat. Your name is Neko."
        ),
    )
    print(response.text)
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/python/system_instruction.py#L22-L33

### Node.js

    // Make sure to include the following import:
    // import {GoogleGenAI} from '@google/genai';
    const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });
    const response = await ai.models.generateContent({
      model: "gemini-2.0-flash",
      contents: "Good morning! How are you?",
      config: {
        systemInstruction: "You are a cat. Your name is Neko.",
      },
    });
    console.log(response.text);
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/javascript/system_instruction.js#L22-L32

### Go

    ctx := context.Background()
    client, err := genai.NewClient(ctx, &genai.ClientConfig{
    	APIKey:  os.Getenv("GEMINI_API_KEY"),
    	Backend: genai.BackendGeminiAPI,
    })
    if err != nil {
    	log.Fatal(err)
    }

    // Construct the user message contents.
    contents := []*genai.Content{
    	genai.NewContentFromText("Good morning! How are you?", genai.RoleUser),
    }

    // Set the system instruction as a *genai.Content.
    config := &genai.GenerateContentConfig{
    	SystemInstruction: genai.NewContentFromText("You are a cat. Your name is Neko.", genai.RoleUser),
    }

    response, err := client.Models.GenerateContent(ctx, "gemini-2.0-flash", contents, config)
    if err != nil {
    	log.Fatal(err)
    }
    printResponse(response)
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/go/system_instruction.go#L13-L36

### Shell

    curl "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=$GEMINI_API_KEY" \
    -H 'Content-Type: application/json' \
    -d '{ "system_instruction": {
        "parts":
          { "text": "You are a cat. Your name is Neko."}},
        "contents": {
          "parts": {
            "text": "Hello there"}}}'
    https://github.com/google-gemini/deprecated-generative-ai-python/blob/7a7cc5474ddaa0255a4410e05361028a24400abd/samples/rest/system_instruction.sh#L4-L12

### Java

    Client client = new Client();

    Part textPart = Part.builder().text("You are a cat. Your name is Neko.").build();

    Content content = Content.builder().role("system").parts(ImmutableList.of(textPart)).build();

    GenerateContentConfig config = GenerateContentConfig.builder()
            .systemInstruction(content)
            .build();

    GenerateContentResponse response =
            client.models.generateContent(
                    "gemini-2.0-flash",
                    "Good morning! How are you?",
                    config);

    System.out.println(response.text());
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/java/src/main/java/com/example/gemini/SystemInstruction.java#L30-L46

### Response body

If successful, the response body contains an instance of [GenerateContentResponse](https://ai.google.dev/api/generate-content#v1beta.GenerateContentResponse).

## Method: models.streamGenerateContent

- [Endpoint](https://ai.google.dev/api/generate-content#body.HTTP_TEMPLATE)
- [Path parameters](https://ai.google.dev/api/generate-content#body.PATH_PARAMETERS)
- [Request body](https://ai.google.dev/api/generate-content#body.request_body)
  - [JSON representation](https://ai.google.dev/api/generate-content#body.request_body.SCHEMA_REPRESENTATION)
- [Response body](https://ai.google.dev/api/generate-content#body.response_body)
- [Authorization scopes](https://ai.google.dev/api/generate-content#body.aspect)
- [Example request](https://ai.google.dev/api/generate-content#body.codeSnippets)
  - [Text](https://ai.google.dev/api/generate-content#body.codeSnippets.group)
  - [Image](https://ai.google.dev/api/generate-content#body.codeSnippets.group_1)
  - [Audio](https://ai.google.dev/api/generate-content#body.codeSnippets.group_2)
  - [Video](https://ai.google.dev/api/generate-content#body.codeSnippets.group_3)
  - [PDF](https://ai.google.dev/api/generate-content#body.codeSnippets.group_4)
  - [Chat](https://ai.google.dev/api/generate-content#body.codeSnippets.group_5)

Generates a [streamed response](https://ai.google.dev/gemini-api/docs/text-generation?lang=python#generate-a-text-stream) from the model given an input `GenerateContentRequest`.

### Endpoint

post `https:``/``/generativelanguage.googleapis.com``/v1beta``/{model=models``/*}:streamGenerateContent`

### Path parameters

`model` `string`
Required. The name of the `Model` to use for generating the completion.

Format: `models/{model}`. It takes the form `models/{model}`.

### Request body

The request body contains data with the following structure:
Fields `contents[]` `object (`[Content](https://ai.google.dev/api/caching#Content)`)`
Required. The content of the current conversation with the model.

For single-turn queries, this is a single instance. For multi-turn queries like [chat](https://ai.google.dev/gemini-api/docs/text-generation#chat), this is a repeated field that contains the conversation history and the latest request.
`tools[]` `object (`[Tool](https://ai.google.dev/api/caching#Tool)`)`
Optional. A list of `Tools` the `Model` may use to generate the next response.

A `Tool` is a piece of code that enables the system to interact with external systems to perform an action, or set of actions, outside of knowledge and scope of the `Model`. Supported `Tool`s are `Function` and `codeExecution`. Refer to the [Function calling](https://ai.google.dev/gemini-api/docs/function-calling) and the [Code execution](https://ai.google.dev/gemini-api/docs/code-execution) guides to learn more.
`toolConfig` `object (`[ToolConfig](https://ai.google.dev/api/caching#ToolConfig)`)`
Optional. Tool configuration for any `Tool` specified in the request. Refer to the [Function calling guide](https://ai.google.dev/gemini-api/docs/function-calling#function_calling_mode) for a usage example.
`safetySettings[]` `object (`[SafetySetting](https://ai.google.dev/api/generate-content#v1beta.SafetySetting)`)`
Optional. A list of unique `SafetySetting` instances for blocking unsafe content.

This will be enforced on the `GenerateContentRequest.contents` and `GenerateContentResponse.candidates`. There should not be more than one setting for each `SafetyCategory` type. The API will block any contents and responses that fail to meet the thresholds set by these settings. This list overrides the default settings for each `SafetyCategory` specified in the safetySettings. If there is no `SafetySetting` for a given `SafetyCategory` provided in the list, the API will use the default safety setting for that category. Harm categories HARM_CATEGORY_HATE_SPEECH, HARM_CATEGORY_SEXUALLY_EXPLICIT, HARM_CATEGORY_DANGEROUS_CONTENT, HARM_CATEGORY_HARASSMENT, HARM_CATEGORY_CIVIC_INTEGRITY are supported. Refer to the [guide](https://ai.google.dev/gemini-api/docs/safety-settings) for detailed information on available safety settings. Also refer to the [Safety guidance](https://ai.google.dev/gemini-api/docs/safety-guidance) to learn how to incorporate safety considerations in your AI applications.
`systemInstruction` `object (`[Content](https://ai.google.dev/api/caching#Content)`)`
Optional. Developer set [system instruction(s)](https://ai.google.dev/gemini-api/docs/system-instructions). Currently, text only.
`generationConfig` `object (`[GenerationConfig](https://ai.google.dev/api/generate-content#v1beta.GenerationConfig)`)`
Optional. Configuration options for model generation and outputs.
`cachedContent` `string`
Optional. The name of the content [cached](https://ai.google.dev/gemini-api/docs/caching) to use as context to serve the prediction. Format: `cachedContents/{cachedContent}`

### Example request

### Text

### Python

    from google import genai

    client = genai.Client()
    response = client.models.generate_content_stream(
        model="gemini-2.0-flash", contents="Write a story about a magic backpack."
    )
    for chunk in response:
        print(chunk.text)
        print("_" * 80)
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/python/text_generation.py#L37-L45

### Node.js

    // Make sure to include the following import:
    // import {GoogleGenAI} from '@google/genai';
    const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });

    const response = await ai.models.generateContentStream({
      model: "gemini-2.0-flash",
      contents: "Write a story about a magic backpack.",
    });
    let text = "";
    for await (const chunk of response) {
      console.log(chunk.text);
      text += chunk.text;
    }
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/javascript/text_generation.js#L51-L63

### Go

    ctx := context.Background()
    client, err := genai.NewClient(ctx, &genai.ClientConfig{
    	APIKey:  os.Getenv("GEMINI_API_KEY"),
    	Backend: genai.BackendGeminiAPI,
    })
    if err != nil {
    	log.Fatal(err)
    }
    contents := []*genai.Content{
    	genai.NewContentFromText("Write a story about a magic backpack.", genai.RoleUser),
    }
    for response, err := range client.Models.GenerateContentStream(
    	ctx,
    	"gemini-2.0-flash",
    	contents,
    	nil,
    ) {
    	if err != nil {
    		log.Fatal(err)
    	}
    	fmt.Print(response.Candidates[0].Content.Parts[0].Text)
    }
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/go/text_generation.go#L38-L59

### Shell

    curl "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:streamGenerateContent?alt=sse&key=${GEMINI_API_KEY}" \
            -H 'Content-Type: application/json' \
            --no-buffer \
            -d '{ "contents":[{"parts":[{"text": "Write a story about a magic backpack."}]}]}'
    https://github.com/google-gemini/deprecated-generative-ai-python/blob/7a7cc5474ddaa0255a4410e05361028a24400abd/samples/rest/text_generation.sh#L33-L37

### Java

    Client client = new Client();

    ResponseStream<GenerateContentResponse> responseStream =
            client.models.generateContentStream(
                    "gemini-2.0-flash",
                    "Write a story about a magic backpack.",
                    null);

    StringBuilder response = new StringBuilder();
    for (GenerateContentResponse res : responseStream) {
        System.out.print(res.text());
        response.append(res.text());
    }

    responseStream.close();
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/java/src/main/java/com/example/gemini/TextGeneration.java#L49-L63

### Image

### Python

    from google import genai
    import PIL.Image

    client = genai.Client()
    organ = PIL.Image.open(media / "organ.jpg")
    response = client.models.generate_content_stream(
        model="gemini-2.0-flash", contents=["Tell me about this instrument", organ]
    )
    for chunk in response:
        print(chunk.text)
        print("_" * 80)
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/python/text_generation.py#L63-L73

### Node.js

    // Make sure to include the following import:
    // import {GoogleGenAI} from '@google/genai';
    const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });

    const organ = await ai.files.upload({
      file: path.join(media, "organ.jpg"),
    });

    const response = await ai.models.generateContentStream({
      model: "gemini-2.0-flash",
      contents: [
        createUserContent([
          "Tell me about this instrument",
          createPartFromUri(organ.uri, organ.mimeType)
        ]),
      ],
    });
    let text = "";
    for await (const chunk of response) {
      console.log(chunk.text);
      text += chunk.text;
    }
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/javascript/text_generation.js#L94-L115

### Go

    ctx := context.Background()
    client, err := genai.NewClient(ctx, &genai.ClientConfig{
    	APIKey:  os.Getenv("GEMINI_API_KEY"),
    	Backend: genai.BackendGeminiAPI,
    })
    if err != nil {
    	log.Fatal(err)
    }
    file, err := client.Files.UploadFromPath(
    	ctx,
    	filepath.Join(getMedia(), "organ.jpg"),
    	&genai.UploadFileConfig{
    		MIMEType : "image/jpeg",
    	},
    )
    if err != nil {
    	log.Fatal(err)
    }
    parts := []*genai.Part{
    	genai.NewPartFromText("Tell me about this instrument"),
    	genai.NewPartFromURI(file.URI, file.MIMEType),
    }
    contents := []*genai.Content{
    	genai.NewContentFromParts(parts, genai.RoleUser),
    }
    for response, err := range client.Models.GenerateContentStream(
    	ctx,
    	"gemini-2.0-flash",
    	contents,
    	nil,
    ) {
    	if err != nil {
    		log.Fatal(err)
    	}
    	fmt.Print(response.Candidates[0].Content.Parts[0].Text)
    }
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/go/text_generation.go#L104-L139

### Shell

    cat > "$TEMP_JSON" << EOF
    {
      "contents": [{
        "parts":[
          {"text": "Tell me about this instrument"},
          {
            "inline_data": {
              "mime_type":"image/jpeg",
              "data": "$(cat "$TEMP_B64")"
            }
          }
        ]
      }]
    }
    EOF

    curl "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:streamGenerateContent?alt=sse&key=$GEMINI_API_KEY" \
        -H 'Content-Type: application/json' \
        -X POST \
        -d "@$TEMP_JSON" 2> /dev/null
    https://github.com/google-gemini/deprecated-generative-ai-python/blob/7a7cc5474ddaa0255a4410e05361028a24400abd/samples/rest/text_generation.sh#L74-L94

### Java

    Client client = new Client();

    String path = media_path + "organ.jpg";
    byte[] imageData = Files.readAllBytes(Paths.get(path));

    Content content =
            Content.fromParts(
                    Part.fromText("Tell me about this instrument."),
                    Part.fromBytes(imageData, "image/jpeg"));


    ResponseStream<GenerateContentResponse> responseStream =
            client.models.generateContentStream(
                    "gemini-2.0-flash",
                    content,
                    null);

    StringBuilder response = new StringBuilder();
    for (GenerateContentResponse res : responseStream) {
        System.out.print(res.text());
        response.append(res.text());
    }

    responseStream.close();
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/java/src/main/java/com/example/gemini/TextGeneration.java#L89-L112

### Audio

### Python

    from google import genai

    client = genai.Client()
    sample_audio = client.files.upload(file=media / "sample.mp3")
    response = client.models.generate_content_stream(
        model="gemini-2.0-flash",
        contents=["Give me a summary of this audio file.", sample_audio],
    )
    for chunk in response:
        print(chunk.text)
        print("_" * 80)
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/python/text_generation.py#L131-L141

### Go

    ctx := context.Background()
    client, err := genai.NewClient(ctx, &genai.ClientConfig{
    	APIKey:  os.Getenv("GEMINI_API_KEY"),
    	Backend: genai.BackendGeminiAPI,
    })
    if err != nil {
    	log.Fatal(err)
    }

    file, err := client.Files.UploadFromPath(
    	ctx,
    	filepath.Join(getMedia(), "sample.mp3"),
    	&genai.UploadFileConfig{
    		MIMEType : "audio/mpeg",
    	},
    )
    if err != nil {
    	log.Fatal(err)
    }

    parts := []*genai.Part{
    	genai.NewPartFromText("Give me a summary of this audio file."),
    	genai.NewPartFromURI(file.URI, file.MIMEType),
    }

    contents := []*genai.Content{
    	genai.NewContentFromParts(parts, genai.RoleUser),
    }

    for result, err := range client.Models.GenerateContentStream(
    	ctx,
    	"gemini-2.0-flash",
    	contents,
    	nil,
    ) {
    	if err != nil {
    		log.Fatal(err)
    	}
    	fmt.Print(result.Candidates[0].Content.Parts[0].Text)
    }
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/go/text_generation.go#L296-L335

### Shell

    # Use File API to upload audio data to API request.
    MIME_TYPE=$(file -b --mime-type "${AUDIO_PATH}")
    NUM_BYTES=$(wc -c < "${AUDIO_PATH}")
    DISPLAY_NAME=AUDIO

    tmp_header_file=upload-header.tmp

    # Initial resumable request defining metadata.
    # The upload url is in the response headers dump them to a file.
    curl "${BASE_URL}/upload/v1beta/files?key=${GEMINI_API_KEY}" \
      -D upload-header.tmp \
      -H "X-Goog-Upload-Protocol: resumable" \
      -H "X-Goog-Upload-Command: start" \
      -H "X-Goog-Upload-Header-Content-Length: ${NUM_BYTES}" \
      -H "X-Goog-Upload-Header-Content-Type: ${MIME_TYPE}" \
      -H "Content-Type: application/json" \
      -d "{'file': {'display_name': '${DISPLAY_NAME}'}}" 2> /dev/null

    upload_url=$(grep -i "x-goog-upload-url: " "${tmp_header_file}" | cut -d" " -f2 | tr -d "\r")
    rm "${tmp_header_file}"

    # Upload the actual bytes.
    curl "${upload_url}" \
      -H "Content-Length: ${NUM_BYTES}" \
      -H "X-Goog-Upload-Offset: 0" \
      -H "X-Goog-Upload-Command: upload, finalize" \
      --data-binary "@${AUDIO_PATH}" 2> /dev/null > file_info.json

    file_uri=$(jq ".file.uri" file_info.json)
    echo file_uri=$file_uri

    curl "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:streamGenerateContent?alt=sse&key=$GEMINI_API_KEY" \
        -H 'Content-Type: application/json' \
        -X POST \
        -d '{
          "contents": [{
            "parts":[
              {"text": "Please describe this file."},
              {"file_data":{"mime_type": "audio/mpeg", "file_uri": '$file_uri'}}]
            }]
           }' 2> /dev/null > response.json

    cat response.json
    echo
    https://github.com/google-gemini/deprecated-generative-ai-python/blob/7a7cc5474ddaa0255a4410e05361028a24400abd/samples/rest/text_generation.sh#L224-L268

### Video

### Python

    from google import genai
    import time

    client = genai.Client()
    # Video clip (CC BY 3.0) from https://peach.blender.org/download/
    myfile = client.files.upload(file=media / "Big_Buck_Bunny.mp4")
    print(f"{myfile=}")

    # Poll until the video file is completely processed (state becomes ACTIVE).
    while not myfile.state or myfile.state.name != "ACTIVE":
        print("Processing video...")
        print("File state:", myfile.state)
        time.sleep(5)
        myfile = client.files.get(name=myfile.name)

    response = client.models.generate_content_stream(
        model="gemini-2.0-flash", contents=[myfile, "Describe this video clip"]
    )
    for chunk in response:
        print(chunk.text)
        print("_" * 80)
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/python/text_generation.py#L169-L189

### Node.js

    // Make sure to include the following import:
    // import {GoogleGenAI} from '@google/genai';
    const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });

    let video = await ai.files.upload({
      file: path.join(media, 'Big_Buck_Bunny.mp4'),
    });

    // Poll until the video file is completely processed (state becomes ACTIVE).
    while (!video.state || video.state.toString() !== 'ACTIVE') {
      console.log('Processing video...');
      console.log('File state: ', video.state);
      await sleep(5000);
      video = await ai.files.get({name: video.name});
    }

    const response = await ai.models.generateContentStream({
      model: "gemini-2.0-flash",
      contents: [
        createUserContent([
          "Describe this video clip",
          createPartFromUri(video.uri, video.mimeType),
        ]),
      ],
    });
    let text = "";
    for await (const chunk of response) {
      console.log(chunk.text);
      text += chunk.text;
    }
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/javascript/text_generation.js#L269-L298

### Go

    ctx := context.Background()
    client, err := genai.NewClient(ctx, &genai.ClientConfig{
    	APIKey:  os.Getenv("GEMINI_API_KEY"),
    	Backend: genai.BackendGeminiAPI,
    })
    if err != nil {
    	log.Fatal(err)
    }

    file, err := client.Files.UploadFromPath(
    	ctx,
    	filepath.Join(getMedia(), "Big_Buck_Bunny.mp4"),
    	&genai.UploadFileConfig{
    		MIMEType : "video/mp4",
    	},
    )
    if err != nil {
    	log.Fatal(err)
    }

    // Poll until the video file is completely processed (state becomes ACTIVE).
    for file.State == genai.FileStateUnspecified || file.State != genai.FileStateActive {
    	fmt.Println("Processing video...")
    	fmt.Println("File state:", file.State)
    	time.Sleep(5 * time.Second)

    	file, err = client.Files.Get(ctx, file.Name, nil)
    	if err != nil {
    		log.Fatal(err)
    	}
    }

    parts := []*genai.Part{
    	genai.NewPartFromText("Describe this video clip"),
    	genai.NewPartFromURI(file.URI, file.MIMEType),
    }

    contents := []*genai.Content{
    	genai.NewContentFromParts(parts, genai.RoleUser),
    }

    for result, err := range client.Models.GenerateContentStream(
    	ctx,
    	"gemini-2.0-flash",
    	contents,
    	nil,
    ) {
    	if err != nil {
    		log.Fatal(err)
    	}
    	fmt.Print(result.Candidates[0].Content.Parts[0].Text)
    }
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/go/text_generation.go#L394-L445

### Shell

    # Use File API to upload audio data to API request.
    MIME_TYPE=$(file -b --mime-type "${VIDEO_PATH}")
    NUM_BYTES=$(wc -c < "${VIDEO_PATH}")
    DISPLAY_NAME=VIDEO_PATH

    # Initial resumable request defining metadata.
    # The upload url is in the response headers dump them to a file.
    curl "${BASE_URL}/upload/v1beta/files?key=${GEMINI_API_KEY}" \
      -D upload-header.tmp \
      -H "X-Goog-Upload-Protocol: resumable" \
      -H "X-Goog-Upload-Command: start" \
      -H "X-Goog-Upload-Header-Content-Length: ${NUM_BYTES}" \
      -H "X-Goog-Upload-Header-Content-Type: ${MIME_TYPE}" \
      -H "Content-Type: application/json" \
      -d "{'file': {'display_name': '${DISPLAY_NAME}'}}" 2> /dev/null

    upload_url=$(grep -i "x-goog-upload-url: " "${tmp_header_file}" | cut -d" " -f2 | tr -d "\r")
    rm "${tmp_header_file}"

    # Upload the actual bytes.
    curl "${upload_url}" \
      -H "Content-Length: ${NUM_BYTES}" \
      -H "X-Goog-Upload-Offset: 0" \
      -H "X-Goog-Upload-Command: upload, finalize" \
      --data-binary "@${VIDEO_PATH}" 2> /dev/null > file_info.json

    file_uri=$(jq ".file.uri" file_info.json)
    echo file_uri=$file_uri

    state=$(jq ".file.state" file_info.json)
    echo state=$state

    while [[ "($state)" = *"PROCESSING"* ]];
    do
      echo "Processing video..."
      sleep 5
      # Get the file of interest to check state
      curl https://generativelanguage.googleapis.com/v1beta/files/$name > file_info.json
      state=$(jq ".file.state" file_info.json)
    done

    curl "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:streamGenerateContent?alt=sse&key=$GEMINI_API_KEY" \
        -H 'Content-Type: application/json' \
        -X POST \
        -d '{
          "contents": [{
            "parts":[
              {"text": "Please describe this file."},
              {"file_data":{"mime_type": "video/mp4", "file_uri": '$file_uri'}}]
            }]
           }' 2> /dev/null > response.json

    cat response.json
    echo
    https://github.com/google-gemini/deprecated-generative-ai-python/blob/7a7cc5474ddaa0255a4410e05361028a24400abd/samples/rest/text_generation.sh#L335-L389

### PDF

### Python

    from google import genai

    client = genai.Client()
    sample_pdf = client.files.upload(file=media / "test.pdf")
    response = client.models.generate_content_stream(
        model="gemini-2.0-flash",
        contents=["Give me a summary of this document:", sample_pdf],
    )

    for chunk in response:
        print(chunk.text)
        print("_" * 80)
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/python/text_generation.py#L207-L218

### Go

    ctx := context.Background()
    client, err := genai.NewClient(ctx, &genai.ClientConfig{
    	APIKey:  os.Getenv("GEMINI_API_KEY"),
    	Backend: genai.BackendGeminiAPI,
    })
    if err != nil {
    	log.Fatal(err)
    }

    file, err := client.Files.UploadFromPath(
    	ctx,
    	filepath.Join(getMedia(), "test.pdf"),
    	&genai.UploadFileConfig{
    		MIMEType : "application/pdf",
    	},
    )
    if err != nil {
    	log.Fatal(err)
    }

    parts := []*genai.Part{
    	genai.NewPartFromText("Give me a summary of this document:"),
    	genai.NewPartFromURI(file.URI, file.MIMEType),
    }

    contents := []*genai.Content{
    	genai.NewContentFromParts(parts, genai.RoleUser),
    }

    for result, err := range client.Models.GenerateContentStream(
    	ctx,
    	"gemini-2.0-flash",
    	contents,
    	nil,
    ) {
    	if err != nil {
    		log.Fatal(err)
    	}
    	fmt.Print(result.Candidates[0].Content.Parts[0].Text)
    }
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/go/text_generation.go#L492-L531

### Shell

    MIME_TYPE=$(file -b --mime-type "${PDF_PATH}")
    NUM_BYTES=$(wc -c < "${PDF_PATH}")
    DISPLAY_NAME=TEXT


    echo $MIME_TYPE
    tmp_header_file=upload-header.tmp

    # Initial resumable request defining metadata.
    # The upload url is in the response headers dump them to a file.
    curl "${BASE_URL}/upload/v1beta/files?key=${GEMINI_API_KEY}" \
      -D upload-header.tmp \
      -H "X-Goog-Upload-Protocol: resumable" \
      -H "X-Goog-Upload-Command: start" \
      -H "X-Goog-Upload-Header-Content-Length: ${NUM_BYTES}" \
      -H "X-Goog-Upload-Header-Content-Type: ${MIME_TYPE}" \
      -H "Content-Type: application/json" \
      -d "{'file': {'display_name': '${DISPLAY_NAME}'}}" 2> /dev/null

    upload_url=$(grep -i "x-goog-upload-url: " "${tmp_header_file}" | cut -d" " -f2 | tr -d "\r")
    rm "${tmp_header_file}"

    # Upload the actual bytes.
    curl "${upload_url}" \
      -H "Content-Length: ${NUM_BYTES}" \
      -H "X-Goog-Upload-Offset: 0" \
      -H "X-Goog-Upload-Command: upload, finalize" \
      --data-binary "@${PDF_PATH}" 2> /dev/null > file_info.json

    file_uri=$(jq ".file.uri" file_info.json)
    echo file_uri=$file_uri

    # Now generate content using that file
    curl "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:streamGenerateContent?alt=sse&key=$GEMINI_API_KEY" \
        -H 'Content-Type: application/json' \
        -X POST \
        -d '{
          "contents": [{
            "parts":[
              {"text": "Can you add a few more lines to this poem?"},
              {"file_data":{"mime_type": "application/pdf", "file_uri": '$file_uri'}}]
            }]
           }' 2> /dev/null > response.json

    cat response.json
    echo
    https://github.com/google-gemini/deprecated-generative-ai-python/blob/7a7cc5474ddaa0255a4410e05361028a24400abd/samples/rest/text_generation.sh#L445-L491

### Chat

### Python

    from google import genai
    from google.genai import types

    client = genai.Client()
    chat = client.chats.create(
        model="gemini-2.0-flash",
        history=[
            types.Content(role="user", parts=[types.Part(text="Hello")]),
            types.Content(
                role="model",
                parts=[
                    types.Part(
                        text="Great to meet you. What would you like to know?"
                    )
                ],
            ),
        ],
    )
    response = chat.send_message_stream(message="I have 2 dogs in my house.")
    for chunk in response:
        print(chunk.text)
        print("_" * 80)
    response = chat.send_message_stream(message="How many paws are in my house?")
    for chunk in response:
        print(chunk.text)
        print("_" * 80)

    print(chat.get_history())
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/python/chat.py#L52-L79

### Node.js

    // Make sure to include the following import:
    // import {GoogleGenAI} from '@google/genai';
    const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });
    const chat = ai.chats.create({
      model: "gemini-2.0-flash",
      history: [
        {
          role: "user",
          parts: [{ text: "Hello" }],
        },
        {
          role: "model",
          parts: [{ text: "Great to meet you. What would you like to know?" }],
        },
      ],
    });

    console.log("Streaming response for first message:");
    const stream1 = await chat.sendMessageStream({
      message: "I have 2 dogs in my house.",
    });
    for await (const chunk of stream1) {
      console.log(chunk.text);
      console.log("_".repeat(80));
    }

    console.log("Streaming response for second message:");
    const stream2 = await chat.sendMessageStream({
      message: "How many paws are in my house?",
    });
    for await (const chunk of stream2) {
      console.log(chunk.text);
      console.log("_".repeat(80));
    }

    console.log(chat.getHistory());
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/javascript/chat.js#L66-L101

### Go

    ctx := context.Background()
    client, err := genai.NewClient(ctx, &genai.ClientConfig{
    	APIKey:  os.Getenv("GEMINI_API_KEY"),
    	Backend: genai.BackendGeminiAPI,
    })
    if err != nil {
    	log.Fatal(err)
    }

    history := []*genai.Content{
    	genai.NewContentFromText("Hello", genai.RoleUser),
    	genai.NewContentFromText("Great to meet you. What would you like to know?", genai.RoleModel),
    }
    chat, err := client.Chats.Create(ctx, "gemini-2.0-flash", nil, history)
    if err != nil {
    	log.Fatal(err)
    }

    for chunk, err := range chat.SendMessageStream(ctx, genai.Part{Text: "I have 2 dogs in my house."}) {
    	if err != nil {
    		log.Fatal(err)
    	}
    	fmt.Println(chunk.Text())
    	fmt.Println(strings.Repeat("_", 64))
    }

    for chunk, err := range chat.SendMessageStream(ctx, genai.Part{Text: "How many paws are in my house?"}) {
    	if err != nil {
    		log.Fatal(err)
    	}
    	fmt.Println(chunk.Text())
    	fmt.Println(strings.Repeat("_", 64))
    }

    fmt.Println(chat.History(false))
    https://github.com/google-gemini/api-examples/blob/856e8a0f566a2810625cecabba6e2ab1fe97e496/go/chat.go#L54-L88

### Shell

    curl https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:streamGenerateContent?alt=sse&key=$GEMINI_API_KEY \
        -H 'Content-Type: application/json' \
        -X POST \
        -d '{
          "contents": [
            {"role":"user",
             "parts":[{
               "text": "Hello"}]},
            {"role": "model",
             "parts":[{
               "text": "Great to meet you. What would you like to know?"}]},
            {"role":"user",
             "parts":[{
               "text": "I have two dogs in my house. How many paws are in my house?"}]},
          ]
        }' 2> /dev/null | grep "text"
    https://github.com/google-gemini/deprecated-generative-ai-python/blob/7a7cc5474ddaa0255a4410e05361028a24400abd/samples/rest/chat.sh#L27-L43

### Response body

If successful, the response body contains a stream of [GenerateContentResponse](https://ai.google.dev/api/generate-content#v1beta.GenerateContentResponse) instances.

## GenerateContentResponse

- [JSON representation](https://ai.google.dev/api/generate-content#SCHEMA_REPRESENTATION)
- [PromptFeedback](https://ai.google.dev/api/generate-content#PromptFeedback)
  - [JSON representation](https://ai.google.dev/api/generate-content#PromptFeedback.SCHEMA_REPRESENTATION)
- [BlockReason](https://ai.google.dev/api/generate-content#BlockReason)
- [UsageMetadata](https://ai.google.dev/api/generate-content#UsageMetadata)
  - [JSON representation](https://ai.google.dev/api/generate-content#UsageMetadata.SCHEMA_REPRESENTATION)
- [ModelStatus](https://ai.google.dev/api/generate-content#ModelStatus)
  - [JSON representation](https://ai.google.dev/api/generate-content#ModelStatus.SCHEMA_REPRESENTATION)
- [ModelStage](https://ai.google.dev/api/generate-content#ModelStage)

Response from the model supporting multiple candidate responses.

Safety ratings and content filtering are reported for both prompt in `GenerateContentResponse.prompt_feedback` and for each candidate in `finishReason` and in `safetyRatings`. The API: - Returns either all requested candidates or none of them - Returns no candidates at all only if there was something wrong with the prompt (check `promptFeedback`) - Reports feedback on each candidate in `finishReason` and `safetyRatings`.
Fields `candidates[]` `object (`[Candidate](https://ai.google.dev/api/generate-content#v1beta.Candidate)`)`
Candidate responses from the model.
`promptFeedback` `object (`[PromptFeedback](https://ai.google.dev/api/generate-content#PromptFeedback)`)`
Returns the prompt's feedback related to the content filters.
`usageMetadata` `object (`[UsageMetadata](https://ai.google.dev/api/generate-content#UsageMetadata)`)`
Output only. Metadata on the generation requests' token usage.
`modelVersion` `string`
Output only. The model version used to generate the response.
`responseId` `string`
Output only. responseId is used to identify each response.
`modelStatus` `object (`[ModelStatus](https://ai.google.dev/api/generate-content#ModelStatus)`)`
Output only. The current model status of this model.

| JSON representation |
|---|
| ``` { "candidates": [ { object (https://ai.google.dev/api/generate-content#v1beta.Candidate) } ], "promptFeedback": { object (https://ai.google.dev/api/generate-content#PromptFeedback) }, "usageMetadata": { object (https://ai.google.dev/api/generate-content#UsageMetadata) }, "modelVersion": string, "responseId": string, "modelStatus": { object (https://ai.google.dev/api/generate-content#ModelStatus) } } ``` |

## PromptFeedback

A set of the feedback metadata the prompt specified in `GenerateContentRequest.content`.
Fields `blockReason` `enum (`[BlockReason](https://ai.google.dev/api/generate-content#BlockReason)`)`
Optional. If set, the prompt was blocked and no candidates are returned. Rephrase the prompt.
`safetyRatings[]` `object (`[SafetyRating](https://ai.google.dev/api/generate-content#v1beta.SafetyRating)`)`
Ratings for safety of the prompt. There is at most one rating per category.

| JSON representation |
|---|
| ``` { "blockReason": enum (https://ai.google.dev/api/generate-content#BlockReason), "safetyRatings": [ { object (https://ai.google.dev/api/generate-content#v1beta.SafetyRating) } ] } ``` |

## BlockReason

Specifies the reason why the prompt was blocked.

| Enums ||
|---|---|
| `BLOCK_REASON_UNSPECIFIED` | Default value. This value is unused. |
| `SAFETY` | Prompt was blocked due to safety reasons. Inspect `safetyRatings` to understand which safety category blocked it. |
| `OTHER` | Prompt was blocked due to unknown reasons. |
| `BLOCKLIST` | Prompt was blocked due to the terms which are included from the terminology blocklist. |
| `PROHIBITED_CONTENT` | Prompt was blocked due to prohibited content. |
| `IMAGE_SAFETY` | Candidates blocked due to unsafe image generation content. |

## UsageMetadata

Metadata on the generation request's token usage.
Fields `promptTokenCount` `integer`
Number of tokens in the prompt. When `cachedContent` is set, this is still the total effective prompt size meaning this includes the number of tokens in the cached content.
`cachedContentTokenCount` `integer`
Number of tokens in the cached part of the prompt (the cached content)
`candidatesTokenCount` `integer`
Total number of tokens across all the generated response candidates.
`toolUsePromptTokenCount` `integer`
Output only. Number of tokens present in tool-use prompt(s).
`thoughtsTokenCount` `integer`
Output only. Number of tokens of thoughts for thinking models.
`totalTokenCount` `integer`
Total token count for the generation request (prompt + response candidates).
`promptTokensDetails[]` `object (`[ModalityTokenCount](https://ai.google.dev/api/generate-content#v1beta.ModalityTokenCount)`)`
Output only. List of modalities that were processed in the request input.
`cacheTokensDetails[]` `object (`[ModalityTokenCount](https://ai.google.dev/api/generate-content#v1beta.ModalityTokenCount)`)`
Output only. List of modalities of the cached content in the request input.
`candidatesTokensDetails[]` `object (`[ModalityTokenCount](https://ai.google.dev/api/generate-content#v1beta.ModalityTokenCount)`)`
Output only. List of modalities that were returned in the response.
`toolUsePromptTokensDetails[]` `object (`[ModalityTokenCount](https://ai.google.dev/api/generate-content#v1beta.ModalityTokenCount)`)`
Output only. List of modalities that were processed for tool-use request inputs.

| JSON representation |
|---|
| ``` { "promptTokenCount": integer, "cachedContentTokenCount": integer, "candidatesTokenCount": integer, "toolUsePromptTokenCount": integer, "thoughtsTokenCount": integer, "totalTokenCount": integer, "promptTokensDetails": [ { object (https://ai.google.dev/api/generate-content#v1beta.ModalityTokenCount) } ], "cacheTokensDetails": [ { object (https://ai.google.dev/api/generate-content#v1beta.ModalityTokenCount) } ], "candidatesTokensDetails": [ { object (https://ai.google.dev/api/generate-content#v1beta.ModalityTokenCount) } ], "toolUsePromptTokensDetails": [ { object (https://ai.google.dev/api/generate-content#v1beta.ModalityTokenCount) } ] } ``` |

## ModelStatus

The status of the underlying model. This is used to indicate the stage of the underlying model and the retirement time if applicable.
Fields `modelStage` `enum (`[ModelStage](https://ai.google.dev/api/generate-content#ModelStage)`)`
The stage of the underlying model.
`retirementTime` `string (`[Timestamp](https://protobuf.dev/reference/protobuf/google.protobuf/#timestamp)` format)`
The time at which the model will be retired.

Uses RFC 3339, where generated output will always be Z-normalized and use 0, 3, 6 or 9 fractional digits. Offsets other than "Z" are also accepted. Examples: `"2014-10-02T15:01:23Z"`, `"2014-10-02T15:01:23.045123456Z"` or `"2014-10-02T15:01:23+05:30"`.
`message` `string`
A message explaining the model status.

| JSON representation |
|---|
| ``` { "modelStage": enum (https://ai.google.dev/api/generate-content#ModelStage), "retirementTime": string, "message": string } ``` |

## ModelStage

Defines the stage of the underlying model.

| Enums ||
|---|---|
| `MODEL_STAGE_UNSPECIFIED` | Unspecified model stage. |
| `UNSTABLE_EXPERIMENTAL` | The underlying model is subject to lots of tunings. | This item is deprecated! |
| `EXPERIMENTAL` | Models in this stage are for experimental purposes only. |
| `PREVIEW` | Models in this stage are more mature than experimental models. |
| `STABLE` | Models in this stage are considered stable and ready for production use. |
| `LEGACY` | If the model is on this stage, it means that this model is on the path to deprecation in near future. Only existing customers can use this model. |
| `DEPRECATED` | Models in this stage are deprecated. These models cannot be used. | This item is deprecated! |
| `RETIRED` | Models in this stage are retired. These models cannot be used. |

## Candidate

- [JSON representation](https://ai.google.dev/api/generate-content#SCHEMA_REPRESENTATION)
- [FinishReason](https://ai.google.dev/api/generate-content#FinishReason)
- [GroundingAttribution](https://ai.google.dev/api/generate-content#GroundingAttribution)
  - [JSON representation](https://ai.google.dev/api/generate-content#GroundingAttribution.SCHEMA_REPRESENTATION)
- [AttributionSourceId](https://ai.google.dev/api/generate-content#AttributionSourceId)
  - [JSON representation](https://ai.google.dev/api/generate-content#AttributionSourceId.SCHEMA_REPRESENTATION)
- [GroundingPassageId](https://ai.google.dev/api/generate-content#GroundingPassageId)
  - [JSON representation](https://ai.google.dev/api/generate-content#GroundingPassageId.SCHEMA_REPRESENTATION)
- [SemanticRetrieverChunk](https://ai.google.dev/api/generate-content#SemanticRetrieverChunk)
  - [JSON representation](https://ai.google.dev/api/generate-content#SemanticRetrieverChunk.SCHEMA_REPRESENTATION)
- [GroundingMetadata](https://ai.google.dev/api/generate-content#GroundingMetadata)
  - [JSON representation](https://ai.google.dev/api/generate-content#GroundingMetadata.SCHEMA_REPRESENTATION)
- [SearchEntryPoint](https://ai.google.dev/api/generate-content#SearchEntryPoint)
  - [JSON representation](https://ai.google.dev/api/generate-content#SearchEntryPoint.SCHEMA_REPRESENTATION)
- [GroundingChunk](https://ai.google.dev/api/generate-content#GroundingChunk)
  - [JSON representation](https://ai.google.dev/api/generate-content#GroundingChunk.SCHEMA_REPRESENTATION)
- [Web](https://ai.google.dev/api/generate-content#Web)
  - [JSON representation](https://ai.google.dev/api/generate-content#Web.SCHEMA_REPRESENTATION)
- [RetrievedContext](https://ai.google.dev/api/generate-content#RetrievedContext)
  - [JSON representation](https://ai.google.dev/api/generate-content#RetrievedContext.SCHEMA_REPRESENTATION)
- [Maps](https://ai.google.dev/api/generate-content#Maps)
  - [JSON representation](https://ai.google.dev/api/generate-content#Maps.SCHEMA_REPRESENTATION)
- [PlaceAnswerSources](https://ai.google.dev/api/generate-content#PlaceAnswerSources)
  - [JSON representation](https://ai.google.dev/api/generate-content#PlaceAnswerSources.SCHEMA_REPRESENTATION)
- [ReviewSnippet](https://ai.google.dev/api/generate-content#ReviewSnippet)
  - [JSON representation](https://ai.google.dev/api/generate-content#ReviewSnippet.SCHEMA_REPRESENTATION)
- [GroundingSupport](https://ai.google.dev/api/generate-content#GroundingSupport)
  - [JSON representation](https://ai.google.dev/api/generate-content#GroundingSupport.SCHEMA_REPRESENTATION)
- [Segment](https://ai.google.dev/api/generate-content#Segment)
  - [JSON representation](https://ai.google.dev/api/generate-content#Segment.SCHEMA_REPRESENTATION)
- [RetrievalMetadata](https://ai.google.dev/api/generate-content#RetrievalMetadata)
  - [JSON representation](https://ai.google.dev/api/generate-content#RetrievalMetadata.SCHEMA_REPRESENTATION)
- [LogprobsResult](https://ai.google.dev/api/generate-content#LogprobsResult)
  - [JSON representation](https://ai.google.dev/api/generate-content#LogprobsResult.SCHEMA_REPRESENTATION)
- [TopCandidates](https://ai.google.dev/api/generate-content#TopCandidates)
  - [JSON representation](https://ai.google.dev/api/generate-content#TopCandidates.SCHEMA_REPRESENTATION)
- [Candidate](https://ai.google.dev/api/generate-content#Candidate)
  - [JSON representation](https://ai.google.dev/api/generate-content#Candidate.SCHEMA_REPRESENTATION)
- [UrlContextMetadata](https://ai.google.dev/api/generate-content#UrlContextMetadata)
  - [JSON representation](https://ai.google.dev/api/generate-content#UrlContextMetadata.SCHEMA_REPRESENTATION)
- [UrlMetadata](https://ai.google.dev/api/generate-content#UrlMetadata)
  - [JSON representation](https://ai.google.dev/api/generate-content#UrlMetadata.SCHEMA_REPRESENTATION)
- [UrlRetrievalStatus](https://ai.google.dev/api/generate-content#UrlRetrievalStatus)

A response candidate generated from the model.
Fields `content` `object (`[Content](https://ai.google.dev/api/caching#Content)`)`
Output only. Generated content returned from the model.
`finishReason` `enum (`[FinishReason](https://ai.google.dev/api/generate-content#FinishReason)`)`
Optional. Output only. The reason why the model stopped generating tokens.

If empty, the model has not stopped generating tokens.
`safetyRatings[]` `object (`[SafetyRating](https://ai.google.dev/api/generate-content#v1beta.SafetyRating)`)`
List of ratings for the safety of a response candidate.

There is at most one rating per category.
`citationMetadata` `object (`[CitationMetadata](https://ai.google.dev/api/generate-content#v1beta.CitationMetadata)`)`
Output only. Citation information for model-generated candidate.

This field may be populated with recitation information for any text included in the `content`. These are passages that are "recited" from copyrighted material in the foundational LLM's training data.
`tokenCount` `integer`
Output only. Token count for this candidate.
`groundingAttributions[]` `object (`[GroundingAttribution](https://ai.google.dev/api/generate-content#GroundingAttribution)`)`
Output only. Attribution information for sources that contributed to a grounded answer.

This field is populated for `GenerateAnswer` calls.
`groundingMetadata` `object (`[GroundingMetadata](https://ai.google.dev/api/generate-content#GroundingMetadata)`)`
Output only. Grounding metadata for the candidate.

This field is populated for `GenerateContent` calls.
`avgLogprobs` `number`
Output only. Average log probability score of the candidate.
`logprobsResult` `object (`[LogprobsResult](https://ai.google.dev/api/generate-content#LogprobsResult)`)`
Output only. Log-likelihood scores for the response tokens and top tokens
`urlContextMetadata` `object (`[UrlContextMetadata](https://ai.google.dev/api/generate-content#UrlContextMetadata)`)`
Output only. Metadata related to url context retrieval tool.
`index` `integer`
Output only. Index of the candidate in the list of response candidates.
`finishMessage` `string`
Optional. Output only. Details the reason why the model stopped generating tokens. This is populated only when `finishReason` is set.

| JSON representation |
|---|
| ``` { "content": { object (https://ai.google.dev/api/caching#Content) }, "finishReason": enum (https://ai.google.dev/api/generate-content#FinishReason), "safetyRatings": [ { object (https://ai.google.dev/api/generate-content#v1beta.SafetyRating) } ], "citationMetadata": { object (https://ai.google.dev/api/generate-content#v1beta.CitationMetadata) }, "tokenCount": integer, "groundingAttributions": [ { object (https://ai.google.dev/api/generate-content#GroundingAttribution) } ], "groundingMetadata": { object (https://ai.google.dev/api/generate-content#GroundingMetadata) }, "avgLogprobs": number, "logprobsResult": { object (https://ai.google.dev/api/generate-content#LogprobsResult) }, "urlContextMetadata": { object (https://ai.google.dev/api/generate-content#UrlContextMetadata) }, "index": integer, "finishMessage": string } ``` |

## FinishReason

Defines the reason why the model stopped generating tokens.

| Enums ||
|---|---|
| `FINISH_REASON_UNSPECIFIED` | Default value. This value is unused. |
| `STOP` | Natural stop point of the model or provided stop sequence. |
| `MAX_TOKENS` | The maximum number of tokens as specified in the request was reached. |
| `SAFETY` | The response candidate content was flagged for safety reasons. |
| `RECITATION` | The response candidate content was flagged for recitation reasons. |
| `LANGUAGE` | The response candidate content was flagged for using an unsupported language. |
| `OTHER` | Unknown reason. |
| `BLOCKLIST` | Token generation stopped because the content contains forbidden terms. |
| `PROHIBITED_CONTENT` | Token generation stopped for potentially containing prohibited content. |
| `SPII` | Token generation stopped because the content potentially contains Sensitive Personally Identifiable Information (SPII). |
| `MALFORMED_FUNCTION_CALL` | The function call generated by the model is invalid. |
| `IMAGE_SAFETY` | Token generation stopped because generated images contain safety violations. |
| `IMAGE_PROHIBITED_CONTENT` | Image generation stopped because generated images has other prohibited content. |
| `IMAGE_OTHER` | Image generation stopped because of other miscellaneous issue. |
| `NO_IMAGE` | The model was expected to generate an image, but none was generated. |
| `IMAGE_RECITATION` | Image generation stopped due to recitation. |
| `UNEXPECTED_TOOL_CALL` | Model generated a tool call but no tools were enabled in the request. |
| `TOO_MANY_TOOL_CALLS` | Model called too many tools consecutively, thus the system exited execution. |
| `MISSING_THOUGHT_SIGNATURE` | Request has at least one thought signature missing. |

## GroundingAttribution

Attribution for a source that contributed to an answer.
Fields `sourceId` `object (`[AttributionSourceId](https://ai.google.dev/api/generate-content#AttributionSourceId)`)`
Output only. Identifier for the source contributing to this attribution.
`content` `object (`[Content](https://ai.google.dev/api/caching#Content)`)`
Grounding source content that makes up this attribution.

| JSON representation |
|---|
| ``` { "sourceId": { object (https://ai.google.dev/api/generate-content#AttributionSourceId) }, "content": { object (https://ai.google.dev/api/caching#Content) } } ``` |

## AttributionSourceId

Identifier for the source contributing to this attribution.
Fields
`source` `Union type`
`source` can be only one of the following:
`groundingPassage` `object (`[GroundingPassageId](https://ai.google.dev/api/generate-content#GroundingPassageId)`)`
Identifier for an inline passage.
`semanticRetrieverChunk` `object (`[SemanticRetrieverChunk](https://ai.google.dev/api/generate-content#SemanticRetrieverChunk)`)`
Identifier for a `Chunk` fetched via Semantic Retriever.

| JSON representation |
|---|
| ``` { // source "groundingPassage": { object (https://ai.google.dev/api/generate-content#GroundingPassageId) }, "semanticRetrieverChunk": { object (https://ai.google.dev/api/generate-content#SemanticRetrieverChunk) } // Union type } ``` |

## GroundingPassageId

Identifier for a part within a `GroundingPassage`.
Fields `passageId` `string`
Output only. ID of the passage matching the `GenerateAnswerRequest`'s `GroundingPassage.id`.
`partIndex` `integer`
Output only. Index of the part within the `GenerateAnswerRequest`'s `GroundingPassage.content`.

| JSON representation |
|---|
| ``` { "passageId": string, "partIndex": integer } ``` |

## SemanticRetrieverChunk

Identifier for a `Chunk` retrieved via Semantic Retriever specified in the `GenerateAnswerRequest` using `SemanticRetrieverConfig`.
Fields `source` `string`
Output only. Name of the source matching the request's `SemanticRetrieverConfig.source`. Example: `corpora/123` or `corpora/123/documents/abc`
`chunk` `string`
Output only. Name of the `Chunk` containing the attributed text. Example: `corpora/123/documents/abc/chunks/xyz`

| JSON representation |
|---|
| ``` { "source": string, "chunk": string } ``` |

## GroundingMetadata

Metadata returned to client when grounding is enabled.
Fields `groundingChunks[]` `object (`[GroundingChunk](https://ai.google.dev/api/generate-content#GroundingChunk)`)`
List of supporting references retrieved from specified grounding source. When streaming, this only contains the grounding chunks that have not been included in the grounding metadata of previous responses.
`groundingSupports[]` `object (`[GroundingSupport](https://ai.google.dev/api/generate-content#GroundingSupport)`)`
List of grounding support.
`webSearchQueries[]` `string`
Web search queries for the following-up web search.
`searchEntryPoint` `object (`[SearchEntryPoint](https://ai.google.dev/api/generate-content#SearchEntryPoint)`)`
Optional. Google search entry for the following-up web searches.
`retrievalMetadata` `object (`[RetrievalMetadata](https://ai.google.dev/api/generate-content#RetrievalMetadata)`)`
Metadata related to retrieval in the grounding flow.
`googleMapsWidgetContextToken` `string`
Optional. Resource name of the Google Maps widget context token that can be used with the PlacesContextElement widget in order to render contextual data. Only populated in the case that grounding with Google Maps is enabled.

| JSON representation |
|---|
| ``` { "groundingChunks": [ { object (https://ai.google.dev/api/generate-content#GroundingChunk) } ], "groundingSupports": [ { object (https://ai.google.dev/api/generate-content#GroundingSupport) } ], "webSearchQueries": [ string ], "searchEntryPoint": { object (https://ai.google.dev/api/generate-content#SearchEntryPoint) }, "retrievalMetadata": { object (https://ai.google.dev/api/generate-content#RetrievalMetadata) }, "googleMapsWidgetContextToken": string } ``` |

## SearchEntryPoint

Google search entry point.
Fields `renderedContent` `string`
Optional. Web content snippet that can be embedded in a web page or an app webview.
`sdkBlob` `string (`[bytes](https://developers.google.com/discovery/v1/type-format)` format)`
Optional. Base64 encoded JSON representing array of \<search term, search url\> tuple.

A base64-encoded string.

| JSON representation |
|---|
| ``` { "renderedContent": string, "sdkBlob": string } ``` |

## GroundingChunk

Grounding chunk.
Fields
`chunk_type` `Union type`
Chunk type. `chunk_type` can be only one of the following:
`web` `object (`[Web](https://ai.google.dev/api/generate-content#Web)`)`
Grounding chunk from the web.
`retrievedContext` `object (`[RetrievedContext](https://ai.google.dev/api/generate-content#RetrievedContext)`)`
Optional. Grounding chunk from context retrieved by the file search tool.
`maps` `object (`[Maps](https://ai.google.dev/api/generate-content#Maps)`)`
Optional. Grounding chunk from Google Maps.

| JSON representation |
|---|
| ``` { // chunk_type "web": { object (https://ai.google.dev/api/generate-content#Web) }, "retrievedContext": { object (https://ai.google.dev/api/generate-content#RetrievedContext) }, "maps": { object (https://ai.google.dev/api/generate-content#Maps) } // Union type } ``` |

## Web

Chunk from the web.
Fields `uri` `string`
URI reference of the chunk.
`title` `string`
Title of the chunk.

| JSON representation |
|---|
| ``` { "uri": string, "title": string } ``` |

## RetrievedContext

Chunk from context retrieved by the file search tool.
Fields `uri` `string`
Optional. URI reference of the semantic retrieval document.
`title` `string`
Optional. Title of the document.
`text` `string`
Optional. Text of the chunk.
`fileSearchStore` `string`
Optional. Name of the `FileSearchStore` containing the document. Example: `fileSearchStores/123`

| JSON representation |
|---|
| ``` { "uri": string, "title": string, "text": string, "fileSearchStore": string } ``` |

## Maps

A grounding chunk from Google Maps. A Maps chunk corresponds to a single place.
Fields `uri` `string`
URI reference of the place.
`title` `string`
Title of the place.
`text` `string`
Text description of the place answer.
`placeId` `string`
This ID of the place, in `places/{placeId}` format. A user can use this ID to look up that place.
`placeAnswerSources` `object (`[PlaceAnswerSources](https://ai.google.dev/api/generate-content#PlaceAnswerSources)`)`
Sources that provide answers about the features of a given place in Google Maps.

| JSON representation |
|---|
| ``` { "uri": string, "title": string, "text": string, "placeId": string, "placeAnswerSources": { object (https://ai.google.dev/api/generate-content#PlaceAnswerSources) } } ``` |

## PlaceAnswerSources

Collection of sources that provide answers about the features of a given place in Google Maps. Each PlaceAnswerSources message corresponds to a specific place in Google Maps. The Google Maps tool used these sources in order to answer questions about features of the place (e.g: "does Bar Foo have Wifi" or "is Foo Bar wheelchair accessible?"). Currently we only support review snippets as sources.
Fields `reviewSnippets[]` `object (`[ReviewSnippet](https://ai.google.dev/api/generate-content#ReviewSnippet)`)`
Snippets of reviews that are used to generate answers about the features of a given place in Google Maps.

| JSON representation |
|---|
| ``` { "reviewSnippets": [ { object (https://ai.google.dev/api/generate-content#ReviewSnippet) } ] } ``` |

## ReviewSnippet

Encapsulates a snippet of a user review that answers a question about the features of a specific place in Google Maps.
Fields `reviewId` `string`
The ID of the review snippet.
`googleMapsUri` `string`
A link that corresponds to the user review on Google Maps.
`title` `string`
Title of the review.

| JSON representation |
|---|
| ``` { "reviewId": string, "googleMapsUri": string, "title": string } ``` |

## GroundingSupport

Grounding support.
Fields `groundingChunkIndices[]` `integer`
Optional. A list of indices (into 'grounding_chunk' in `response.candidate.grounding_metadata`) specifying the citations associated with the claim. For instance \[1,3,4\] means that grounding_chunk\[1\], grounding_chunk\[3\], grounding_chunk\[4\] are the retrieved content attributed to the claim. If the response is streaming, the groundingChunkIndices refer to the indices across all responses. It is the client's responsibility to accumulate the grounding chunks from all responses (while maintaining the same order).
`confidenceScores[]` `number`
Optional. Confidence score of the support references. Ranges from 0 to 1. 1 is the most confident. This list must have the same size as the groundingChunkIndices.
`segment` `object (`[Segment](https://ai.google.dev/api/generate-content#Segment)`)`
Segment of the content this support belongs to.

| JSON representation |
|---|
| ``` { "groundingChunkIndices": [ integer ], "confidenceScores": [ number ], "segment": { object (https://ai.google.dev/api/generate-content#Segment) } } ``` |

## Segment

Segment of the content.
Fields `partIndex` `integer`
The index of a Part object within its parent Content object.
`startIndex` `integer`
Start index in the given Part, measured in bytes. Offset from the start of the Part, inclusive, starting at zero.
`endIndex` `integer`
End index in the given Part, measured in bytes. Offset from the start of the Part, exclusive, starting at zero.
`text` `string`
The text corresponding to the segment from the response.

| JSON representation |
|---|
| ``` { "partIndex": integer, "startIndex": integer, "endIndex": integer, "text": string } ``` |

## RetrievalMetadata

Metadata related to retrieval in the grounding flow.
Fields `googleSearchDynamicRetrievalScore` `number`
Optional. Score indicating how likely information from google search could help answer the prompt. The score is in the range \[0, 1\], where 0 is the least likely and 1 is the most likely. This score is only populated when google search grounding and dynamic retrieval is enabled. It will be compared to the threshold to determine whether to trigger google search.

| JSON representation |
|---|
| ``` { "googleSearchDynamicRetrievalScore": number } ``` |

## LogprobsResult

Logprobs Result
Fields `topCandidates[]` `object (`[TopCandidates](https://ai.google.dev/api/generate-content#TopCandidates)`)`
Length = total number of decoding steps.
`chosenCandidates[]` `object (`[Candidate](https://ai.google.dev/api/generate-content#Candidate)`)`
Length = total number of decoding steps. The chosen candidates may or may not be in topCandidates.
`logProbabilitySum` `number`
Sum of log probabilities for all tokens.

| JSON representation |
|---|
| ``` { "topCandidates": [ { object (https://ai.google.dev/api/generate-content#TopCandidates) } ], "chosenCandidates": [ { object (https://ai.google.dev/api/generate-content#Candidate) } ], "logProbabilitySum": number } ``` |

## TopCandidates

Candidates with top log probabilities at each decoding step.
Fields `candidates[]` `object (`[Candidate](https://ai.google.dev/api/generate-content#Candidate)`)`
Sorted by log probability in descending order.

| JSON representation |
|---|
| ``` { "candidates": [ { object (https://ai.google.dev/api/generate-content#Candidate) } ] } ``` |

## Candidate

Candidate for the logprobs token and score.
Fields `token` `string`
The candidate's token string value.
`tokenId` `integer`
The candidate's token id value.
`logProbability` `number`
The candidate's log probability.

| JSON representation |
|---|
| ``` { "token": string, "tokenId": integer, "logProbability": number } ``` |

## UrlContextMetadata

Metadata related to url context retrieval tool.
Fields `urlMetadata[]` `object (`[UrlMetadata](https://ai.google.dev/api/generate-content#UrlMetadata)`)`
List of url context.

| JSON representation |
|---|
| ``` { "urlMetadata": [ { object (https://ai.google.dev/api/generate-content#UrlMetadata) } ] } ``` |

## UrlMetadata

Context of the a single url retrieval.
Fields `retrievedUrl` `string`
Retrieved url by the tool.
`urlRetrievalStatus` `enum (`[UrlRetrievalStatus](https://ai.google.dev/api/generate-content#UrlRetrievalStatus)`)`
Status of the url retrieval.

| JSON representation |
|---|
| ``` { "retrievedUrl": string, "urlRetrievalStatus": enum (https://ai.google.dev/api/generate-content#UrlRetrievalStatus) } ``` |

## UrlRetrievalStatus

Status of the url retrieval.

| Enums ||
|---|---|
| `URL_RETRIEVAL_STATUS_UNSPECIFIED` | Default value. This value is unused. |
| `URL_RETRIEVAL_STATUS_SUCCESS` | Url retrieval is successful. |
| `URL_RETRIEVAL_STATUS_ERROR` | Url retrieval is failed due to error. |
| `URL_RETRIEVAL_STATUS_PAYWALL` | Url retrieval is failed because the content is behind paywall. |
| `URL_RETRIEVAL_STATUS_UNSAFE` | Url retrieval is failed because the content is unsafe. |

## CitationMetadata

- [JSON representation](https://ai.google.dev/api/generate-content#SCHEMA_REPRESENTATION)
- [CitationSource](https://ai.google.dev/api/generate-content#CitationSource)
  - [JSON representation](https://ai.google.dev/api/generate-content#CitationSource.SCHEMA_REPRESENTATION)

A collection of source attributions for a piece of content.
Fields `citationSources[]` `object (`[CitationSource](https://ai.google.dev/api/generate-content#CitationSource)`)`
Citations to sources for a specific response.

| JSON representation |
|---|
| ``` { "citationSources": [ { object (https://ai.google.dev/api/generate-content#CitationSource) } ] } ``` |

## CitationSource

A citation to a source for a portion of a specific response.
Fields `startIndex` `integer`
Optional. Start of segment of the response that is attributed to this source.

Index indicates the start of the segment, measured in bytes.
`endIndex` `integer`
Optional. End of the attributed segment, exclusive.
`uri` `string`
Optional. URI that is attributed as a source for a portion of the text.
`license` `string`
Optional. License for the GitHub project that is attributed as a source for segment.

License info is required for code citations.

| JSON representation |
|---|
| ``` { "startIndex": integer, "endIndex": integer, "uri": string, "license": string } ``` |

## GenerationConfig

- [JSON representation](https://ai.google.dev/api/generate-content#SCHEMA_REPRESENTATION)
- [Modality](https://ai.google.dev/api/generate-content#Modality)
- [SpeechConfig](https://ai.google.dev/api/generate-content#SpeechConfig)
  - [JSON representation](https://ai.google.dev/api/generate-content#SpeechConfig.SCHEMA_REPRESENTATION)
- [VoiceConfig](https://ai.google.dev/api/generate-content#VoiceConfig)
  - [JSON representation](https://ai.google.dev/api/generate-content#VoiceConfig.SCHEMA_REPRESENTATION)
- [PrebuiltVoiceConfig](https://ai.google.dev/api/generate-content#PrebuiltVoiceConfig)
  - [JSON representation](https://ai.google.dev/api/generate-content#PrebuiltVoiceConfig.SCHEMA_REPRESENTATION)
- [MultiSpeakerVoiceConfig](https://ai.google.dev/api/generate-content#MultiSpeakerVoiceConfig)
  - [JSON representation](https://ai.google.dev/api/generate-content#MultiSpeakerVoiceConfig.SCHEMA_REPRESENTATION)
- [SpeakerVoiceConfig](https://ai.google.dev/api/generate-content#SpeakerVoiceConfig)
  - [JSON representation](https://ai.google.dev/api/generate-content#SpeakerVoiceConfig.SCHEMA_REPRESENTATION)
- [ThinkingConfig](https://ai.google.dev/api/generate-content#ThinkingConfig)
  - [JSON representation](https://ai.google.dev/api/generate-content#ThinkingConfig.SCHEMA_REPRESENTATION)
- [ThinkingLevel](https://ai.google.dev/api/generate-content#ThinkingLevel)
- [ImageConfig](https://ai.google.dev/api/generate-content#ImageConfig)
  - [JSON representation](https://ai.google.dev/api/generate-content#ImageConfig.SCHEMA_REPRESENTATION)
- [MediaResolution](https://ai.google.dev/api/generate-content#MediaResolution)

Configuration options for model generation and outputs. Not all parameters are configurable for every model.
Fields `stopSequences[]` `string`
Optional. The set of character sequences (up to 5) that will stop output generation. If specified, the API will stop at the first appearance of a `stop_sequence`. The stop sequence will not be included as part of the response.
`responseMimeType` `string`
Optional. MIME type of the generated candidate text. Supported MIME types are: `text/plain`: (default) Text output. `application/json`: JSON response in the response candidates. `text/x.enum`: ENUM as a string response in the response candidates. Refer to the [docs](https://ai.google.dev/gemini-api/docs/prompting_with_media#plain_text_formats) for a list of all supported text MIME types.
`responseSchema` `object (`[Schema](https://ai.google.dev/api/caching#Schema)`)`
Optional. Output schema of the generated candidate text. Schemas must be a subset of the [OpenAPI schema](https://spec.openapis.org/oas/v3.0.3#schema) and can be objects, primitives or arrays.

If set, a compatible `responseMimeType` must also be set. Compatible MIME types: `application/json`: Schema for JSON response. Refer to the [JSON text generation guide](https://ai.google.dev/gemini-api/docs/json-mode) for more details.
`_responseJsonSchema` `value (`[Value](https://protobuf.dev/reference/protobuf/google.protobuf/#value)` format)`
Optional. Output schema of the generated response. This is an alternative to `responseSchema` that accepts [JSON Schema](https://json-schema.org/).

If set, `responseSchema` must be omitted, but `responseMimeType` is required.

While the full JSON Schema may be sent, not all features are supported. Specifically, only the following properties are supported:

- `$id`
- `$defs`
- `$ref`
- `$anchor`
- `type`
- `format`
- `title`
- `description`
- `enum` (for strings and numbers)
- `items`
- `prefixItems`
- `minItems`
- `maxItems`
- `minimum`
- `maximum`
- `anyOf`
- `oneOf` (interpreted the same as `anyOf`)
- `properties`
- `additionalProperties`
- `required`

The non-standard `propertyOrdering` property may also be set.

Cyclic references are unrolled to a limited degree and, as such, may only be used within non-required properties. (Nullable properties are not sufficient.) If `$ref` is set on a sub-schema, no other properties, except for than those starting as a `$`, may be set.
`responseJsonSchema` `value (`[Value](https://protobuf.dev/reference/protobuf/google.protobuf/#value)` format)`
Optional. An internal detail. Use `responseJsonSchema` rather than this field.
`responseModalities[]` `enum (`[Modality](https://ai.google.dev/api/generate-content#Modality)`)`
Optional. The requested modalities of the response. Represents the set of modalities that the model can return, and should be expected in the response. This is an exact match to the modalities of the response.

A model may have multiple combinations of supported modalities. If the requested modalities do not match any of the supported combinations, an error will be returned.

An empty list is equivalent to requesting only text.
`candidateCount` `integer`
Optional. Number of generated responses to return. If unset, this will default to 1. Please note that this doesn't work for previous generation models (Gemini 1.0 family)
`maxOutputTokens` `integer`
Optional. The maximum number of tokens to include in a response candidate.

Note: The default value varies by model, see the `Model.output_token_limit` attribute of the `Model` returned from the `getModel` function.
`temperature` `number`
Optional. Controls the randomness of the output.

Note: The default value varies by model, see the `Model.temperature` attribute of the `Model` returned from the `getModel` function.

Values can range from \[0.0, 2.0\].
`topP` `number`
Optional. The maximum cumulative probability of tokens to consider when sampling.

The model uses combined Top-k and Top-p (nucleus) sampling.

Tokens are sorted based on their assigned probabilities so that only the most likely tokens are considered. Top-k sampling directly limits the maximum number of tokens to consider, while Nucleus sampling limits the number of tokens based on the cumulative probability.

Note: The default value varies by `Model` and is specified by the`Model.top_p` attribute returned from the `getModel` function. An empty `topK` attribute indicates that the model doesn't apply top-k sampling and doesn't allow setting `topK` on requests.
`topK` `integer`
Optional. The maximum number of tokens to consider when sampling.

Gemini models use Top-p (nucleus) sampling or a combination of Top-k and nucleus sampling. Top-k sampling considers the set of `topK` most probable tokens. Models running with nucleus sampling don't allow topK setting.

Note: The default value varies by `Model` and is specified by the`Model.top_p` attribute returned from the `getModel` function. An empty `topK` attribute indicates that the model doesn't apply top-k sampling and doesn't allow setting `topK` on requests.
`seed` `integer`
Optional. Seed used in decoding. If not set, the request uses a randomly generated seed.
`presencePenalty` `number`
Optional. Presence penalty applied to the next token's logprobs if the token has already been seen in the response.

This penalty is binary on/off and not dependant on the number of times the token is used (after the first). Use [frequencyPenalty](https://ai.google.dev/api/generate-content#FIELDS.frequency_penalty) for a penalty that increases with each use.

A positive penalty will discourage the use of tokens that have already been used in the response, increasing the vocabulary.

A negative penalty will encourage the use of tokens that have already been used in the response, decreasing the vocabulary.
`frequencyPenalty` `number`
Optional. Frequency penalty applied to the next token's logprobs, multiplied by the number of times each token has been seen in the respponse so far.

A positive penalty will discourage the use of tokens that have already been used, proportional to the number of times the token has been used: The more a token is used, the more difficult it is for the model to use that token again increasing the vocabulary of responses.

Caution: A *negative* penalty will encourage the model to reuse tokens proportional to the number of times the token has been used. Small negative values will reduce the vocabulary of a response. Larger negative values will cause the model to start repeating a common token until it hits the [maxOutputTokens](https://ai.google.dev/api/generate-content#FIELDS.max_output_tokens) limit.
`responseLogprobs` `boolean`
Optional. If true, export the logprobs results in response.
`logprobs` `integer`
Optional. Only valid if [responseLogprobs=True](https://ai.google.dev/api/generate-content#FIELDS.response_logprobs). This sets the number of top logprobs to return at each decoding step in the [Candidate.logprobs_result](https://ai.google.dev/api/generate-content#FIELDS.logprobs_result). The number must be in the range of \[0, 20\].
`enableEnhancedCivicAnswers` `boolean`
Optional. Enables enhanced civic answers. It may not be available for all models.
`speechConfig` `object (`[SpeechConfig](https://ai.google.dev/api/generate-content#SpeechConfig)`)`
Optional. The speech generation config.
`thinkingConfig` `object (`[ThinkingConfig](https://ai.google.dev/api/generate-content#ThinkingConfig)`)`
Optional. Config for thinking features. An error will be returned if this field is set for models that don't support thinking.
`imageConfig` `object (`[ImageConfig](https://ai.google.dev/api/generate-content#ImageConfig)`)`
Optional. Config for image generation. An error will be returned if this field is set for models that don't support these config options.
`mediaResolution` `enum (`[MediaResolution](https://ai.google.dev/api/generate-content#MediaResolution)`)`
Optional. If specified, the media resolution specified will be used.

| JSON representation |
|---|
| ``` { "stopSequences": [ string ], "responseMimeType": string, "responseSchema": { object (https://ai.google.dev/api/caching#Schema) }, "_responseJsonSchema": value, "responseJsonSchema": value, "responseModalities": [ enum (https://ai.google.dev/api/generate-content#Modality) ], "candidateCount": integer, "maxOutputTokens": integer, "temperature": number, "topP": number, "topK": integer, "seed": integer, "presencePenalty": number, "frequencyPenalty": number, "responseLogprobs": boolean, "logprobs": integer, "enableEnhancedCivicAnswers": boolean, "speechConfig": { object (https://ai.google.dev/api/generate-content#SpeechConfig) }, "thinkingConfig": { object (https://ai.google.dev/api/generate-content#ThinkingConfig) }, "imageConfig": { object (https://ai.google.dev/api/generate-content#ImageConfig) }, "mediaResolution": enum (https://ai.google.dev/api/generate-content#MediaResolution) } ``` |

## Modality

Supported modalities of the response.

| Enums ||
|---|---|
| `MODALITY_UNSPECIFIED` | Default value. |
| `TEXT` | Indicates the model should return text. |
| `IMAGE` | Indicates the model should return images. |
| `AUDIO` | Indicates the model should return audio. |

## SpeechConfig

The speech generation config.
Fields `voiceConfig` `object (`[VoiceConfig](https://ai.google.dev/api/generate-content#VoiceConfig)`)`
The configuration in case of single-voice output.
`multiSpeakerVoiceConfig` `object (`[MultiSpeakerVoiceConfig](https://ai.google.dev/api/generate-content#MultiSpeakerVoiceConfig)`)`
Optional. The configuration for the multi-speaker setup. It is mutually exclusive with the voiceConfig field.
`languageCode` `string`
Optional. Language code (in BCP 47 format, e.g. "en-US") for speech synthesis.

Valid values are: de-DE, en-AU, en-GB, en-IN, en-US, es-US, fr-FR, hi-IN, pt-BR, ar-XA, es-ES, fr-CA, id-ID, it-IT, ja-JP, tr-TR, vi-VN, bn-IN, gu-IN, kn-IN, ml-IN, mr-IN, ta-IN, te-IN, nl-NL, ko-KR, cmn-CN, pl-PL, ru-RU, and th-TH.

| JSON representation |
|---|
| ``` { "voiceConfig": { object (https://ai.google.dev/api/generate-content#VoiceConfig) }, "multiSpeakerVoiceConfig": { object (https://ai.google.dev/api/generate-content#MultiSpeakerVoiceConfig) }, "languageCode": string } ``` |

## VoiceConfig

The configuration for the voice to use.
Fields
`voice_config` `Union type`
The configuration for the speaker to use. `voice_config` can be only one of the following:
`prebuiltVoiceConfig` `object (`[PrebuiltVoiceConfig](https://ai.google.dev/api/generate-content#PrebuiltVoiceConfig)`)`
The configuration for the prebuilt voice to use.

| JSON representation |
|---|
| ``` { // voice_config "prebuiltVoiceConfig": { object (https://ai.google.dev/api/generate-content#PrebuiltVoiceConfig) } // Union type } ``` |

## PrebuiltVoiceConfig

The configuration for the prebuilt speaker to use.
Fields `voiceName` `string`
The name of the preset voice to use.

| JSON representation |
|---|
| ``` { "voiceName": string } ``` |

## MultiSpeakerVoiceConfig

The configuration for the multi-speaker setup.
Fields `speakerVoiceConfigs[]` `object (`[SpeakerVoiceConfig](https://ai.google.dev/api/generate-content#SpeakerVoiceConfig)`)`
Required. All the enabled speaker voices.

| JSON representation |
|---|
| ``` { "speakerVoiceConfigs": [ { object (https://ai.google.dev/api/generate-content#SpeakerVoiceConfig) } ] } ``` |

## SpeakerVoiceConfig

The configuration for a single speaker in a multi speaker setup.
Fields `speaker` `string`
Required. The name of the speaker to use. Should be the same as in the prompt.
`voiceConfig` `object (`[VoiceConfig](https://ai.google.dev/api/generate-content#VoiceConfig)`)`
Required. The configuration for the voice to use.

| JSON representation |
|---|
| ``` { "speaker": string, "voiceConfig": { object (https://ai.google.dev/api/generate-content#VoiceConfig) } } ``` |

## ThinkingConfig

Config for thinking features.
Fields `includeThoughts` `boolean`
Indicates whether to include thoughts in the response. If true, thoughts are returned only when available.
`thinkingBudget` `integer`
The number of thoughts tokens that the model should generate.
`thinkingLevel` `enum (`[ThinkingLevel](https://ai.google.dev/api/generate-content#ThinkingLevel)`)`
Optional. Controls the maximum depth of the model's internal reasoning process before it produces a response. If not specified, the default is HIGH. Recommended for Gemini 3 or later models. Use with earlier models results in an error.

| JSON representation |
|---|
| ``` { "includeThoughts": boolean, "thinkingBudget": integer, "thinkingLevel": enum (https://ai.google.dev/api/generate-content#ThinkingLevel) } ``` |

## ThinkingLevel

Allow user to specify how much to think using enum instead of integer budget.

| Enums ||
|---|---|
| `THINKING_LEVEL_UNSPECIFIED` | Default value. |
| `MINIMAL` | Little to no thinking. |
| `LOW` | Low thinking level. |
| `MEDIUM` | Medium thinking level. |
| `HIGH` | High thinking level. |

## ImageConfig

Config for image generation features.
Fields `aspectRatio` `string`
Optional. The aspect ratio of the image to generate. Supported aspect ratios: `1:1`, `2:3`, `3:2`, `3:4`, `4:3`, `4:5`, `5:4`, `9:16`, `16:9`, or `21:9`.

If not specified, the model will choose a default aspect ratio based on any reference images provided.
`imageSize` `string`
Optional. Specifies the size of generated images. Supported values are `1K`, `2K`, `4K`. If not specified, the model will use default value `1K`.

| JSON representation |
|---|
| ``` { "aspectRatio": string, "imageSize": string } ``` |

## MediaResolution

Media resolution for the input media.

| Enums ||
|---|---|
| `MEDIA_RESOLUTION_UNSPECIFIED` | Media resolution has not been set. |
| `MEDIA_RESOLUTION_LOW` | Media resolution set to low (64 tokens). |
| `MEDIA_RESOLUTION_MEDIUM` | Media resolution set to medium (256 tokens). |
| `MEDIA_RESOLUTION_HIGH` | Media resolution set to high (zoomed reframing with 256 tokens). |

## HarmCategory

The category of a rating.

These categories cover various kinds of harms that developers may wish to adjust.

| Enums ||
|---|---|
| `HARM_CATEGORY_UNSPECIFIED` | Category is unspecified. |
| `HARM_CATEGORY_DEROGATORY` | **PaLM** - Negative or harmful comments targeting identity and/or protected attribute. |
| `HARM_CATEGORY_TOXICITY` | **PaLM** - Content that is rude, disrespectful, or profane. |
| `HARM_CATEGORY_VIOLENCE` | **PaLM** - Describes scenarios depicting violence against an individual or group, or general descriptions of gore. |
| `HARM_CATEGORY_SEXUAL` | **PaLM** - Contains references to sexual acts or other lewd content. |
| `HARM_CATEGORY_MEDICAL` | **PaLM** - Promotes unchecked medical advice. |
| `HARM_CATEGORY_DANGEROUS` | **PaLM** - Dangerous content that promotes, facilitates, or encourages harmful acts. |
| `HARM_CATEGORY_HARASSMENT` | **Gemini** - Harassment content. |
| `HARM_CATEGORY_HATE_SPEECH` | **Gemini** - Hate speech and content. |
| `HARM_CATEGORY_SEXUALLY_EXPLICIT` | **Gemini** - Sexually explicit content. |
| `HARM_CATEGORY_DANGEROUS_CONTENT` | **Gemini** - Dangerous content. |
| `HARM_CATEGORY_CIVIC_INTEGRITY` | **Gemini** - Content that may be used to harm civic integrity. DEPRECATED: use enableEnhancedCivicAnswers instead. | This item is deprecated! |

## ModalityTokenCount

- [JSON representation](https://ai.google.dev/api/generate-content#SCHEMA_REPRESENTATION)
- [Modality](https://ai.google.dev/api/generate-content#Modality)

Represents token counting info for a single modality.
Fields `modality` `enum (`[Modality](https://ai.google.dev/api/generate-content#Modality)`)`
The modality associated with this token count.
`tokenCount` `integer`
Number of tokens.

| JSON representation |
|---|
| ``` { "modality": enum (https://ai.google.dev/api/generate-content#Modality), "tokenCount": integer } ``` |

## Modality

Content Part modality

| Enums ||
|---|---|
| `MODALITY_UNSPECIFIED` | Unspecified modality. |
| `TEXT` | Plain text. |
| `IMAGE` | Image. |
| `VIDEO` | Video. |
| `AUDIO` | Audio. |
| `DOCUMENT` | Document, e.g. PDF. |

## SafetyRating

- [JSON representation](https://ai.google.dev/api/generate-content#SCHEMA_REPRESENTATION)
- [HarmProbability](https://ai.google.dev/api/generate-content#HarmProbability)

Safety rating for a piece of content.

The safety rating contains the category of harm and the harm probability level in that category for a piece of content. Content is classified for safety across a number of harm categories and the probability of the harm classification is included here.
Fields `category` `enum (`[HarmCategory](https://ai.google.dev/api/generate-content#v1beta.HarmCategory)`)`
Required. The category for this rating.
`probability` `enum (`[HarmProbability](https://ai.google.dev/api/generate-content#HarmProbability)`)`
Required. The probability of harm for this content.
`blocked` `boolean`
Was this content blocked because of this rating?

| JSON representation |
|---|
| ``` { "category": enum (https://ai.google.dev/api/generate-content#v1beta.HarmCategory), "probability": enum (https://ai.google.dev/api/generate-content#HarmProbability), "blocked": boolean } ``` |

## HarmProbability

The probability that a piece of content is harmful.

The classification system gives the probability of the content being unsafe. This does not indicate the severity of harm for a piece of content.

| Enums ||
|---|---|
| `HARM_PROBABILITY_UNSPECIFIED` | Probability is unspecified. |
| `NEGLIGIBLE` | Content has a negligible chance of being unsafe. |
| `LOW` | Content has a low chance of being unsafe. |
| `MEDIUM` | Content has a medium chance of being unsafe. |
| `HIGH` | Content has a high chance of being unsafe. |

## SafetySetting

- [JSON representation](https://ai.google.dev/api/generate-content#SCHEMA_REPRESENTATION)
- [HarmBlockThreshold](https://ai.google.dev/api/generate-content#HarmBlockThreshold)

Safety setting, affecting the safety-blocking behavior.

Passing a safety setting for a category changes the allowed probability that content is blocked.
Fields `category` `enum (`[HarmCategory](https://ai.google.dev/api/generate-content#v1beta.HarmCategory)`)`
Required. The category for this setting.
`threshold` `enum (`[HarmBlockThreshold](https://ai.google.dev/api/generate-content#HarmBlockThreshold)`)`
Required. Controls the probability threshold at which harm is blocked.

| JSON representation |
|---|
| ``` { "category": enum (https://ai.google.dev/api/generate-content#v1beta.HarmCategory), "threshold": enum (https://ai.google.dev/api/generate-content#HarmBlockThreshold) } ``` |

## HarmBlockThreshold

Block at and beyond a specified harm probability.

| Enums ||
|---|---|
| `HARM_BLOCK_THRESHOLD_UNSPECIFIED` | Threshold is unspecified. |
| `BLOCK_LOW_AND_ABOVE` | Content with NEGLIGIBLE will be allowed. |
| `BLOCK_MEDIUM_AND_ABOVE` | Content with NEGLIGIBLE and LOW will be allowed. |
| `BLOCK_ONLY_HIGH` | Content with NEGLIGIBLE, LOW, and MEDIUM will be allowed. |
| `BLOCK_NONE` | All content will be allowed. |
| `OFF` | Turn off the safety filter. |
