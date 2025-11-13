/**
 * Test script to populate database with 100+ messages
 *
 * Usage: Open browser console and run:
 *   const script = document.createElement('script');
 *   script.type = 'module';
 *   script.src = '/static/services/test_search_performance.js';
 *   document.head.appendChild(script);
 */

import { storage } from './storage.js';

async function populateTestData() {
    console.log('🔄 Starting test data population...');

    const testMessages = [
        // User messages
        "Hello, I need help with family scheduling",
        "My daughter has soccer practice on Tuesdays",
        "Can you help me track everyone's activities?",
        "What about meal planning for next week?",
        "I'm allergic to dairy products",
        "My son prefers vegetarian meals",
        "How do I coordinate carpooling?",
        "We need to organize birthday party planning",
        "What's the best way to manage household chores?",
        "I want to set up a family calendar",

        // Agent responses
        "I can help you organize your family schedule. Let me start by understanding your weekly routine.",
        "I've noted that soccer practice is on Tuesdays. What time does it start?",
        "For activity tracking, I recommend creating separate calendars for each family member.",
        "Meal planning works best when we consider everyone's preferences and dietary restrictions.",
        "I've recorded your dairy allergy. I'll suggest dairy-free recipes.",
        "Vegetarian meal options are great! I can suggest plant-based recipes.",
        "Carpooling coordination requires knowing the schedules of other families. Would you like help with that?",
        "Birthday party planning involves several steps: venue, guest list, food, activities. Let's break it down.",
        "Household chores can be divided fairly using a rotating schedule. Would you like me to create one?",
        "I can sync with your existing calendar apps. Which ones do you use?",

        // More technical queries
        "How do I export my family data?",
        "Can I set up notifications for appointments?",
        "What about privacy settings for shared calendars?",
        "I need to archive old conversations",
        "How do I search through past messages?",
        "Can I customize the theme colors?",
        "What keyboard shortcuts are available?",
        "How do I backup my data?",
        "Can I integrate with Google Calendar?",
        "What's the storage limit for messages?",

        // Problem-solving scenarios
        "My son is having trouble with homework schedules",
        "We need to reduce screen time for the kids",
        "How can we improve family communication?",
        "I want to track health appointments",
        "We're planning a family vacation",
        "Need help with budget planning",
        "Want to set up emergency contacts",
        "How to handle schedule conflicts?",
        "Need reminders for medication",
        "Want to organize family photos",
    ];

    const conversationTopics = [
        "Family Scheduling",
        "Meal Planning",
        "Activity Tracking",
        "Health Management",
        "Budget Planning",
        "Vacation Planning",
        "Homework Help",
        "Emergency Planning"
    ];

    try {
        // Create multiple conversations
        const conversations = [];
        for (let i = 0; i < conversationTopics.length; i++) {
            const convId = await storage.createConversation(conversationTopics[i]);
            conversations.push(convId);
        }

        console.log(`✅ Created ${conversations.length} conversations`);

        // Add messages to conversations
        let totalMessages = 0;
        for (const convId of conversations) {
            // Add 15-20 messages per conversation
            const messageCount = 15 + Math.floor(Math.random() * 6);

            for (let i = 0; i < messageCount; i++) {
                const isUser = i % 2 === 0;
                const messageText = testMessages[Math.floor(Math.random() * testMessages.length)];

                await storage.saveMessage(convId, {
                    type: isUser ? 'user_message' : 'agent_message',
                    message: messageText,
                    timestamp: new Date(Date.now() - (messageCount - i) * 3600000).toISOString()
                });

                totalMessages++;
            }
        }

        console.log(`✅ Added ${totalMessages} messages`);
        console.log(`✅ Test data population complete!`);
        console.log(`\n📊 Summary:`);
        console.log(`   - Conversations: ${conversations.length}`);
        console.log(`   - Messages: ${totalMessages}`);
        console.log(`\n🔍 Try searching for:`);
        console.log(`   - "family"`);
        console.log(`   - "schedule"`);
        console.log(`   - "meal planning"`);
        console.log(`   - "calendar"`);
        console.log(`   - "help"`);

        return {
            conversations: conversations.length,
            messages: totalMessages
        };
    } catch (error) {
        console.error('❌ Failed to populate test data:', error);
        throw error;
    }
}

// Performance test function
async function testSearchPerformance(query) {
    console.log(`\n⚡ Testing search performance for: "${query}"`);

    const iterations = 10;
    const times = [];

    for (let i = 0; i < iterations; i++) {
        const start = performance.now();
        const results = await storage.searchMessages(query);
        const end = performance.now();
        const duration = end - start;
        times.push(duration);

        if (i === 0) {
            console.log(`   First run: ${duration.toFixed(2)}ms (${results.length} results)`);
        }
    }

    const avgTime = times.reduce((a, b) => a + b, 0) / times.length;
    const minTime = Math.min(...times);
    const maxTime = Math.max(...times);

    console.log(`\n📊 Performance Stats (${iterations} runs):`);
    console.log(`   Average: ${avgTime.toFixed(2)}ms`);
    console.log(`   Min: ${minTime.toFixed(2)}ms`);
    console.log(`   Max: ${maxTime.toFixed(2)}ms`);

    if (avgTime < 100) {
        console.log(`   ✅ EXCELLENT - Under 100ms target`);
    } else if (avgTime < 200) {
        console.log(`   ⚠️  ACCEPTABLE - Under 200ms`);
    } else {
        console.log(`   ❌ SLOW - Over 200ms, needs optimization`);
    }

    return {
        avgTime,
        minTime,
        maxTime,
        times
    };
}

// Export functions
export { populateTestData, testSearchPerformance };

// Auto-run if script is loaded directly
console.log('🧪 Search Performance Test Module Loaded');
console.log('\nAvailable functions:');
console.log('  - populateTestData(): Add 100+ test messages');
console.log('  - testSearchPerformance(query): Measure search speed');
console.log('\nExample usage:');
console.log('  import { populateTestData, testSearchPerformance } from "/static/services/test_search_performance.js";');
console.log('  await populateTestData();');
console.log('  await testSearchPerformance("family");');
