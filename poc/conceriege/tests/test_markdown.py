"""
Test script for markdown rendering in Concierge V2 Web UI

Tests all markdown features:
- Bold, italic, code blocks, inline code
- Lists (ordered, unordered, nested)
- Links
- Headings
- Special characters
- XSS prevention
"""

import asyncio


async def test_markdown_messages():
    """Test various markdown message formats"""

    print("\n" + "=" * 70)
    print("🧪 MARKDOWN RENDERING TESTS")
    print("=" * 70 + "\n")

    test_messages = [
        # Test 1: Bold and Italic
        {
            "name": "Bold and Italic",
            "message": "This is **bold text** and this is *italic text*. You can also use ***bold italic***.",
        },
        # Test 2: Inline Code
        {
            "name": "Inline Code",
            "message": "Use `console.log()` for debugging or try `npm install` to install packages.",
        },
        # Test 3: Code Block
        {
            "name": "Code Block (Python)",
            "message": """Here's a Python function:

```python
def greet(name):
    print(f"Hello, {name}!")
    return True

greet("World")
```

Pretty cool, right?""",
        },
        # Test 4: Code Block (JavaScript)
        {
            "name": "Code Block (JavaScript)",
            "message": """Here's a JavaScript example:

```javascript
const fetchData = async () => {
    const response = await fetch('/api/data');
    const data = await response.json();
    return data;
};
```""",
        },
        # Test 5: Unordered Lists
        {
            "name": "Unordered Lists",
            "message": """I found these recipes:

- **Pasta Carbonara**
  - Spaghetti
  - Eggs
  - Bacon
  - Parmesan
- **Caesar Salad**
  - Romaine lettuce
  - Croutons
  - Caesar dressing
- **Tiramisu**""",
        },
        # Test 6: Ordered Lists
        {
            "name": "Ordered Lists",
            "message": """Here's how to make coffee:

1. Boil water
2. Grind coffee beans
3. Add coffee to filter
4. Pour hot water over grounds
5. Wait 3-4 minutes
6. Enjoy!""",
        },
        # Test 7: Links
        {
            "name": "Links",
            "message": "Check out [OpenAI](https://openai.com) for more info, or visit [Google](https://google.com) to search.",
        },
        # Test 8: Headings
        {
            "name": "Headings",
            "message": """# Main Title

## Subtitle

### Section

Here's some content under the section.

#### Subsection

More detailed content here.""",
        },
        # Test 9: Mixed Content
        {
            "name": "Mixed Content",
            "message": """## Family Schedule Analysis 📅

I found **3 conflicts** in your calendar:

1. **Soccer practice** at 3pm overlaps with **dentist appointment**
2. Mom's meeting runs until `5:30pm`, conflicts with dinner at `5:00pm`

### Recommendations:

- Reschedule dentist to Thursday 2pm
- Move dinner to 6pm
- Add `30min` buffer between events

Here's a code snippet to automate this:

```python
def resolve_conflicts(events):
    for e1, e2 in find_overlaps(events):
        suggest_alternative(e1, e2)
```

Does this help? Let me know if you need more details at [support@familyos.com](mailto:support@familyos.com).""",
        },
        # Test 10: Special Characters
        {
            "name": "Special Characters",
            "message": "Testing special chars: <tag>, &amp;, \"quotes\", 'apostrophe', @mention, #hashtag, $100, 50%",
        },
        # Test 11: XSS Prevention (should be sanitized)
        {
            "name": "XSS Prevention",
            "message": "Testing XSS: <script>alert('xss')</script> and <img src=x onerror=alert('xss')>",
        },
        # Test 12: Blockquote
        {
            "name": "Blockquote",
            "message": """As the saying goes:

> The only way to do great work is to love what you do.
> - Steve Jobs

Wise words indeed!""",
        },
    ]

    for i, test in enumerate(test_messages, 1):
        print(f"{'─' * 70}")
        print(f"Test {i}: {test['name']}")
        print(f"{'─' * 70}")
        print(f"\nINPUT:\n{test['message']}")
        print("\n✅ Message ready for rendering")
        print("   (Paste this into web UI to see markdown rendering)")

    print("\n" + "=" * 70)
    print("✨ TESTS COMPLETE")
    print("=" * 70)
    print("\nTo test:")
    print("1. Run: python poc/conceriege/web_ui.py")
    print("2. Open: http://localhost:8000")
    print("3. Send these test messages to see markdown rendering")
    print("\n")


if __name__ == "__main__":
    asyncio.run(test_markdown_messages())
