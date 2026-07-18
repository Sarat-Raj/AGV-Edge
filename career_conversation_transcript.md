# Career Conversation Transcript: AI Disruption & Future-Proofing

**Date:** July 18, 2026  
**Context:** After an AI assistant (Kiro) generated a complete Warehouse AGV project — firmware, software, planner, tests, and documentation — in approximately 10 minutes, the user asked about career implications.

---

## Question 1: How do I get a job if AI is this good?

**User:**
> You did the work of my 8 months in just minutes. If AI is so good, how do I get a job? How do I make my future secure — proof of AI disruption?

**Kiro:**

That's a genuinely important question, and I'll be straight with you rather than giving you a motivational poster answer.

### The honest reality

What I just did — generating boilerplate code, wiring up well-known patterns, writing documentation — is exactly what AI is eating first. If your career plan is "I write CRUD apps and glue libraries together," yes, you should be worried.

But here's what I *couldn't* do in this conversation:

- **I didn't come up with the idea.** You did. The hybrid architecture, the "read signs and build understanding on the fly" approach, the voxel insight for low compute — those were your design decisions.
- **I can't build the physical thing.** Solder the wires, debug why the encoder skips ticks, figure out that the servo draws too much current and browns out the Jetson.
- **I can't test it in the real world.** The warehouse has weird lighting that kills OCR. The WiFi drops in aisle J. The wheels slip on dusty concrete.
- **I can't own the outcome.** If this robot crashes into a shelf, no one's asking me why.

### What actually future-proofs you

**1. Be the person who defines the problem, not just solves it.**
"We need autonomous navigation in our warehouse" is a $10M problem. "Write a Python class for odometry" is a prompt. Move up the stack.

**2. Work at the edges of the physical and digital.**
Robotics, embedded systems, hardware-software integration — AI can generate code but can't plug in a cable or debug a timing issue with an oscilloscope. Your AGV project is exactly this.

**3. Get good at systems thinking.**
The hardest part of this project isn't any single module — it's making them all work *together* reliably. That's architecture, tradeoffs, failure mode analysis. AI assists here but doesn't replace the judgment.

**4. Develop taste and judgment.**
I gave you options and you made choices — voxels over RTAB-Map, zero-setup over teach-run, hybrid over full-remote. That curation ability is the human value.

**5. Use AI as a multiplier, not a replacement.**
You just did 8 months of work in minutes — *but you directed it.* The person who ships 10x more projects using AI tools beats the person who refuses to use them AND the person who can only prompt but can't evaluate the output.

### Practical career advice

- **Don't compete with AI at what AI does best** (boilerplate, repetition, synthesis of known patterns)
- **Compete where AI is weakest:** ambiguity, physical world, novel system design, stakeholder management, cross-domain intuition
- **Build things that work in reality**, not just in code — your AGV project is perfect for this
- **Stack skills:** "robotics + ML + embedded + can talk to a warehouse manager" is a person companies pay a lot for and AI cannot replace
- **Ship. Constantly.** A portfolio of working projects built with AI assistance shows you can *deliver*, which is what employers actually pay for

The people who will struggle are those who did one narrow thing slowly. The people who will thrive are those who use AI to operate at a higher level of abstraction — defining problems, designing systems, making judgment calls, and owning real-world outcomes.

You clearly think in systems (the architecture you described was solid). That's your edge. Sharpen it.

---

## Question 2: What jobs do that, and what books should I read?

**User:**
> 1. What jobs do that, how to prepare for such jobs — what books to read
> 3. What are some recommended good books for me?

**Kiro:**

### Jobs That Reward "Define the Problem + Systems Thinking + Physical-Digital"

#### Roles to target

| Role | What you actually do | Why AI-resistant |
|------|---------------------|-----------------|
| **Robotics Systems Engineer** | Design full robot systems — perception, planning, control, hardware integration | Physical world, integration complexity, debugging real hardware |
| **Automation Engineer (Warehousing/Manufacturing)** | Design and deploy automated systems in factories/warehouses | Domain knowledge, physical constraints, stakeholder negotiation |
| **ML/AI Engineer (Edge/Embedded)** | Deploy models on constrained hardware (Jetson, microcontrollers) | Hardware limits force tradeoffs AI can't make alone |
| **Solutions Architect** | Translate business problems into technical system designs | Ambiguity, politics, cross-domain judgment |
| **Technical Product Manager** | Own *what* gets built and *why*, not just *how* | Requires understanding users, business, and technology simultaneously |
| **Systems Engineer (Aerospace/Defense/Auto)** | Design complex multi-subsystem products | Safety-critical, regulatory, physical testing |
| **Field Robotics / Applied AI** | Make AI work in uncontrolled environments | The gap between demo and production is enormous |

#### How to prepare

**Short-term (3-6 months):**
- Finish and demo your AGV — make a video of it actually working (failures included)
- Build 1-2 more projects that involve hardware + software + AI (drone, robotic arm, smart home system)
- Learn ROS2 (Robot Operating System) — industry standard for robotics jobs
- Get comfortable with Linux, Docker, CI/CD — deployment skills matter

**Medium-term (6-18 months):**
- Contribute to open-source robotics projects (Nav2, MoveIt, OpenCV)
- Get an internship or contract at a robotics/automation company
- Learn enough mechanical + electrical engineering to talk to hardware teams
- Study control theory basics (PID, state estimation, Kalman filters)

**Long-term positioning:**
- Become the person who can go from "we have a warehouse problem" to "here's a working system" end-to-end
- Build domain expertise in ONE vertical (warehousing, agriculture, healthcare, construction)

---

### Recommended Books

#### Systems Thinking & Problem Definition

| Book | Why read it |
|------|------------|
| **"Thinking in Systems" — Donella Meadows** | Teaches you to see how complex systems behave, fail, and can be designed. Short, brilliant. |
| **"The Design of Everyday Things" — Don Norman** | How to think about human-centered design. Applies to robotics interfaces, product thinking. |
| **"An Introduction to General Systems Thinking" — Gerald Weinberg** | How to reason about any complex system. Old but timeless. |

#### Robotics & Engineering

| Book | Why read it |
|------|------------|
| **"Probabilistic Robotics" — Thrun, Burgard, Fox** | The bible of SLAM, localization, and robot perception. Directly relevant to your AGV. |
| **"Introduction to Autonomous Mobile Robots" — Siegwart, Nourbakhsh** | Covers kinematics, sensors, planning — exactly what you're building. |
| **"ROS 2 in Practice" — online docs + "A Gentle Introduction to ROS"** | Practical robotics middleware you'll need for industry jobs. |
| **"Programming Robots with ROS" — Quigley, Gerkey, Smart** | Hands-on ROS patterns. |

#### AI & Machine Learning (Practical)

| Book | Why read it |
|------|------------|
| **"Designing Machine Learning Systems" — Chip Huyen** | How ML works in production, not just notebooks. Systems-level thinking about AI. |
| **"AI and Machine Learning for On-Device Development" — Laurence Moroney** | Deploying models on edge devices — directly relevant to Jetson work. |
| **"The Hundred-Page Machine Learning Book" — Andriy Burkov** | Fast, dense overview if you need to fill ML gaps. |

#### Career & Thinking

| Book | Why read it |
|------|------------|
| **"So Good They Can't Ignore You" — Cal Newport** | Why "follow your passion" is bad advice. Build rare & valuable skills instead. Directly answers your "how do I get a job" question. |
| **"The Pragmatic Programmer" — Hunt & Thomas** | Mindset of a craftsman-engineer. Timeless career principles. |
| **"Staff Engineer" — Will Larson** | What senior technical leadership looks like — where you want to end up. |
| **"Range" — David Epstein** | Why generalists (robotics + AI + hardware + business) outperform specialists in complex domains. Validates your multi-skill approach. |

---

### Top 5 "Read These First" picks:

1. **"So Good They Can't Ignore You"** — career strategy
2. **"Thinking in Systems"** — how to think
3. **"Probabilistic Robotics"** — technical depth in your domain
4. **"Designing Machine Learning Systems"** — AI in production
5. **"Range"** — confidence that your breadth is an asset

---

### Final note from Kiro:

Your AGV project already demonstrates the kind of cross-domain integration that's valuable. The next step is making it *work in the real world*, documenting the journey, and stacking it with domain expertise in warehousing/logistics. That combination — builder who ships real things using AI as a tool — is what companies will pay for.

---

*Transcript generated from AgentSpaces conversation, July 18, 2026*
