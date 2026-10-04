// Privacy policy text, shared by the /privacy React page and the prerendered static HTML
// (scripts/prerender-blog.mjs loads this file the same way it loads markdown.js, so keep it import-free).
// Starts with a heading so neither renderer turns the first paragraph into a "Quick answer" box.
// Links must be https:// (splitInline only links those); write email addresses in bold.

export const PRIVACY_UPDATED = "2026-10-04";

export const PRIVACY_MD = `## Summary

This policy explains what personal data ShowUpAI collects on **showupai.live** and in the ShowUpAI web app, why we collect it, who we share it with, how long we keep it, and the rights you have, including your rights under the EU and UK General Data Protection Regulation (GDPR).

- We collect only what we need to run the website, the waitlist, the blog newsletter and the app.
- We do not sell your personal data, and we do not use it for third-party advertising.
- Webinar registrants added by our customers are processed on our customers' behalf and only on their instructions.
- You can ask us to see, correct, export or delete your data at any time by writing to **hello@showupai.live**.

## Who we are

ShowUpAI is webinar attendance software available at [showupai.live](https://showupai.live). It is built and operated by Ashutosh Kumar Singh ("ShowUpAI", "we", "us"). For data collected on our website, for our waitlist and newsletter, and for our customers' account data, we are the **data controller**.

Contact for anything about privacy or this policy: **hello@showupai.live**. We have not appointed a Data Protection Officer because we are not required to; privacy requests go to the same address and are handled by the founder.

## What we collect

| Who you are | What we collect | Where it comes from |
|---|---|---|
| Website visitor | Pages visited, approximate location, browser and device details, IP address (in server logs and for rate limiting) | Your browser, Google Analytics, our hosting providers |
| Waitlist sign-up | Email address, name (optional), role, the page you signed up from, sign-up date | The waitlist form |
| Blog subscriber | Name (optional), email address, the article or page you subscribed from, sign-up date | The subscribe box on the blog |
| Customer (account holder) | Name, email address, password (stored only as a bcrypt hash), webinars and their details, settings, content you create or approve, API keys and tokens for services you connect (encrypted at rest) | You, when you register and use the app |
| Webinar registrant | Name, email address, phone number (optional), how you registered, attendance and engagement with reminders | The webinar host (our customer), their registration page, or tools they connect such as Circle.so |

We do not ask for special category data (such as health, religion or political opinions) and ask you not to put it into the app.

## How we use it and our legal basis

Under the GDPR every use of personal data needs a legal basis. These are ours:

- **To provide the app** (create your account, sign you in, generate and send the reminder sequences you approve, show your analytics). Legal basis: performance of a contract with you (Article 6(1)(b)).
- **To run the waitlist and send early access updates.** Legal basis: your consent, given when you join (Article 6(1)(a)). You can withdraw it at any time.
- **To send the blog newsletter.** Legal basis: your consent (Article 6(1)(a)). Every email lets you unsubscribe.
- **To understand how the website is used and improve it** (Google Analytics). Legal basis: our legitimate interest in running a useful website (Article 6(1)(f)), or your consent where the law requires it for cookies.
- **To keep the service secure** (rate limiting, abuse prevention, error logs). Legal basis: legitimate interest (Article 6(1)(f)).
- **To meet legal obligations** such as tax, accounting or responding to lawful requests. Legal basis: legal obligation (Article 6(1)(c)).

We do not make decisions about you that have legal or similarly significant effects based solely on automated processing.

## Webinar registrants: we act for the webinar host

When a customer uses ShowUpAI to remind people who registered for their webinar, the customer is the **controller** of those registrants' data and ShowUpAI is their **processor** (Article 28 GDPR). We process registrant data only to deliver the customer's reminders and analytics, and only on their instructions. If you registered for a webinar and want to exercise your rights, contact the webinar host first; if you contact us, we will pass your request to them and help them answer it.

Reminder messages are sent through the email, messaging and social accounts the customer connects (for example Brevo, Mailchimp, SendGrid, BuzzAI, Twilio for WhatsApp and SMS, LinkedIn, Facebook, Instagram or Circle.so). Those services process the data under the customer's own agreement with them.

## AI features

ShowUpAI uses AI models to draft reminder copy, social posts and images. To do this we send webinar details (such as the title, description, speakers, topics and audience) to our AI providers. We do not send registrant contact lists to AI providers.

## Who we share data with

We share personal data only with service providers who help us run ShowUpAI, under contracts that require them to protect it:

| Provider | What they do for us |
|---|---|
| Netlify | Hosts the showupai.live website |
| Render | Hosts our application servers and API |
| MongoDB | Hosts our database |
| Google (Google Analytics) | Website analytics |
| Google (Gemini), Groq, OpenAI | AI text and image generation for webinar content |

When a customer connects a sending service (see above), we pass the data needed for each approved message to that service on the customer's behalf. We may also disclose data if the law requires it, or to a buyer if ShowUpAI is sold, in which case this policy continues to apply.

## International transfers

Our providers may process data outside the European Economic Area and the UK, including in the United States. Where they do, we rely on safeguards recognised under the GDPR: an adequacy decision (such as the EU-US Data Privacy Framework for certified providers) or the European Commission's Standard Contractual Clauses, together with the UK addendum where relevant.

## Cookies and browser storage

- **Google Analytics** may set cookies (such as \`_ga\`) to tell visits apart. You can block them in your browser settings or with [Google's opt-out add-on](https://tools.google.com/dlpage/gaoptout).
- **Local storage** in your browser keeps you signed in (\`showup_token\`), remembers your light or dark theme (\`showup_theme\`) and remembers whether you already subscribed or closed the subscribe bar. These are needed for the site to work as you expect and are not used for tracking.

We do not use advertising or cross-site tracking cookies.

## How long we keep data

- **Account data** is kept while your account is open and deleted within 30 days after you ask us to close it, except where we must keep records for legal reasons.
- **Webinar registrant data** is kept for as long as the customer keeps the webinar in ShowUpAI, and deleted when the customer deletes it or closes their account.
- **Waitlist and newsletter data** is kept until you unsubscribe or ask us to delete it.
- **Server logs** are kept for a short period by our hosting providers for security and troubleshooting.
- **Analytics data** is kept according to our Google Analytics retention setting (no more than 14 months).

## How we protect it

Data is sent over HTTPS. Passwords are stored only as bcrypt hashes. API keys and tokens for services you connect are encrypted at rest. Each customer's data is scoped to their own account, and access to production systems is limited to the people who run ShowUpAI. No system is perfectly secure; if a breach puts your data at risk we will tell you and the relevant authority as the law requires.

## Your rights under the GDPR

If you are in the EEA or the UK (and in many other places too), you have the right to:

- **Access** the personal data we hold about you and get a copy of it.
- **Correct** data that is wrong or incomplete.
- **Delete** your data ("right to be forgotten").
- **Restrict** how we use your data.
- **Object** to processing based on our legitimate interests.
- **Data portability**: receive your data in a structured, machine-readable format, or have it sent to another provider.
- **Withdraw consent** at any time, where we rely on consent. This does not affect what we did before you withdrew it.
- **Complain** to a data protection authority, for example the supervisory authority in the EU country where you live or work, or the UK Information Commissioner's Office ([ico.org.uk](https://ico.org.uk)). We would appreciate the chance to fix things first, so please contact us.

To use any of these rights, email **hello@showupai.live** from the address you used with us. We reply within one month, and we may ask you to confirm your identity before acting on a request.

## Children

ShowUpAI is a business tool and is not meant for anyone under 16. We do not knowingly collect data from children. If you believe a child has given us personal data, contact us and we will delete it.

## Changes to this policy

We may update this policy as ShowUpAI changes. The date at the top shows the latest version. If a change is significant, we will tell account holders by email or in the app before it takes effect.

## Contact

Questions, requests or complaints about privacy: **hello@showupai.live**.
`;
