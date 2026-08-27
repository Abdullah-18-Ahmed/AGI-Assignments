import asyncio
import json
import os
from dataclasses import dataclass, field, asdict
from dotenv import load_dotenv
from openai import AsyncOpenAI
from agents import Agent, OpenAIChatCompletionsModel, Runner, function_tool, RunContextWrapper, ModelSettings, handoff, StopAtTools, MaxTurnsExceeded
from agents.items import HandoffCallItem, HandoffOutputItem
from agents.tracing import set_tracing_export_api_key, trace

load_dotenv()

openai_key = os.getenv("OPENAI_API_KEY")
if openai_key and openai_key != "your-openai-key-here":
    set_tracing_export_api_key(openai_key)

client = AsyncOpenAI(
    api_key=os.getenv("GEMINI_API_KEY"),
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
)

model = OpenAIChatCompletionsModel(
    model="gemini-3.6-flash",
    openai_client=client,
)

gentle_model = OpenAIChatCompletionsModel(
    model="gemini-3.6-flash",
    openai_client=client,
)

strict_model = OpenAIChatCompletionsModel(
    model="gemini-3.6-flash",
    openai_client=client,
)

writer_model = OpenAIChatCompletionsModel(
    model="gemini-3.6-flash",
    openai_client=client,
)

grader_model = OpenAIChatCompletionsModel(
    model="gemini-3.6-flash",
    openai_client=client,
)


PROFILE_FILE = "student_profile.json"


@dataclass
class StudentProfile:
    name: str
    level: str
    weak_topics: list[str] = field(default_factory=list)
    answered: dict[str, dict[str, int]] = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict):
        return cls(**data)


def load_profile() -> StudentProfile | None:
    if os.path.exists(PROFILE_FILE):
        with open(PROFILE_FILE, "r") as f:
            data = json.load(f)
            return StudentProfile.from_dict(data)
    return None


def save_profile(profile: StudentProfile):
    with open(PROFILE_FILE, "w") as f:
        json.dump(profile.to_dict(), f, indent=2)


def load_topics():
    with open("topics.json", "r") as f:
        return json.load(f)


def get_topic_title(topic_id: str) -> str:
    topics = load_topics()
    for t in topics:
        if t["id"] == topic_id:
            return t["title"]
    return topic_id


def dynamic_instructions(ctx: RunContextWrapper[StudentProfile], agent: Agent) -> str:
    profile = ctx.context
    if profile is None:
        return f"You are {agent.name}, a personalized tutor."
    
    topics = load_topics()

    lines = [
        f"You are {agent.name}, a personalized tutor for {profile.name}.",
        f"Student level: {profile.level}.",
    ]

    if profile.weak_topics:
        weak_titles = [get_topic_title(tid) for tid in profile.weak_topics]
        lines.append(f"Focus on weak topics: {', '.join(weak_titles)}. Prioritize these in quizzes.")
    else:
        lines.append("No weak topics identified yet. Assess broadly.")

    strong_topics = []
    for tid, stats in profile.answered.items():
        if stats["total"] > 0:
            accuracy = stats["correct"] / stats["total"]
            if accuracy >= 0.7:
                strong_topics.append((get_topic_title(tid), accuracy))

    if strong_topics:
        strong_str = ", ".join([f"{t} ({a:.0%})" for t, a in strong_topics])
        lines.append(f"Topics mastered (>70%): {strong_str}. For these, ask harder, application-focused questions.")

    lines.append("Quiz flow: 1) Call write_question(topic_id) to get a question. 2) Show it to the student. 3) Take their answer. 4) Call grade_answer(question, student_answer, key_facts). 5) Call record_answer(topic_id, was_correct). 6) Repeat or ask if they want another topic.")

    lines.append("\nHANDOFF RULE: If the student has 2 or more incorrect answers on the CURRENT topic (check profile.answered[topic_id].total - profile.answered[topic_id].correct >= 2), you MUST hand off to the Remedial Tutor for a first-principles explanation before continuing. Use the handoff tool.")

    return "\n".join(lines)


def gentle_instructions(ctx: RunContextWrapper[StudentProfile], agent: Agent) -> str:
    base = dynamic_instructions(ctx, agent)
    return base + "\n\nTone: encouraging, patient, supportive. Celebrate effort. Give hints before answers."


def strict_instructions(ctx: RunContextWrapper[StudentProfile], agent: Agent) -> str:
    base = dynamic_instructions(ctx, agent)
    return base + "\n\nTone: rigorous, concise, demanding. No hand-holding. Wrong answers get direct correction only."


question_writer = Agent(
    name="QuestionWriter",
    instructions="You write exactly ONE quiz question on the given topic. Output only the question text, nothing else. Make it clear and specific. Adapt difficulty to the student's level if provided.",
    model=writer_model,
    model_settings=ModelSettings(temperature=0.9),
)

grader = Agent(
    name="Grader",
    instructions="You grade a student's answer. Input: question, student_answer, key_facts (list). Output ONLY a valid JSON object with exactly these keys: 'verdict' (correct/incorrect/partial) and 'feedback' (exactly one sentence). No markdown, no code blocks, no extra text. Example: {\"verdict\": \"correct\", \"feedback\": \"Answer correctly identifies all key components.\"}",
    model=grader_model,
    model_settings=ModelSettings(temperature=0.1, max_tokens=500),
)


remedial_tutor = Agent(
    name="Remedial Tutor",
    instructions="You explain a topic from first principles with a clear, step-by-step worked example. No quizzing. Structure: 1) Core concept in plain language. 2) Why it matters. 3) Worked example with annotations. 4) Common pitfalls. 5) One practice problem (no grading). Adapt depth to student level from context.",
    model=model,
    model_settings=ModelSettings(temperature=0.4),
)


@function_tool
def list_topics() -> list[dict]:
    """Return all topic IDs and titles."""
    topics = load_topics()
    return [{"id": t["id"], "title": t["title"]} for t in topics]


@function_tool
def get_notes(topic_id: str) -> dict:
    """Return summary and key facts for a topic by ID."""
    topics = load_topics()
    for topic in topics:
        if topic["id"] == topic_id:
            return {"summary": topic["summary"], "key_facts": topic["key_facts"]}
    return {"error": f"Topic {topic_id} not found"}


@function_tool
def record_answer(ctx: RunContextWrapper[StudentProfile], topic_id: str, was_correct: bool) -> str:
    """Record a quiz answer for the current student."""
    profile = ctx.context
    if topic_id not in profile.answered:
        profile.answered[topic_id] = {"correct": 0, "total": 0}
    profile.answered[topic_id]["total"] += 1
    if was_correct:
        profile.answered[topic_id]["correct"] += 1
    else:
        if topic_id not in profile.weak_topics:
            profile.weak_topics.append(topic_id)
    return f"Recorded answer for {topic_id}: {'correct' if was_correct else 'incorrect'}"


@function_tool(is_enabled=lambda ctx, agent: getattr(ctx.context, 'level', None) == "intermediate")
def start_exam_mode(ctx: RunContextWrapper[StudentProfile]) -> str:
    """Start exam mode: timed, scored assessment across all topics. Only for intermediate+ students."""
    return "Exam mode started. You will be quizzed on all topics with a time limit."


@function_tool
def finish_session(ctx: RunContextWrapper[StudentProfile]) -> str:
    """End the current tutoring session."""
    raise StopAtTools("Session ended by student.")


base_tools = [
    list_topics,
    get_notes,
    record_answer,
    start_exam_mode,
    finish_session,
    question_writer.as_tool(
        tool_name="write_question",
        tool_description="Write a single quiz question for a topic. Input: topic_id, student_level.",
    ),
    grader.as_tool(
        tool_name="grade_answer",
        tool_description="Grade a student's answer. Input: question, student_answer, key_facts.",
    ),
]

handoffs = [handoff(remedial_tutor)]

agent = Agent(
    name="Study Buddy",
    instructions=dynamic_instructions,
    model=model,
    tools=base_tools,
    handoffs=handoffs,
)

gentle_agent = Agent(
    name="Study Buddy (Gentle)",
    instructions=gentle_instructions,
    model=gentle_model,
    model_settings=ModelSettings(temperature=0.3),
    tools=base_tools,
    handoffs=handoffs,
)

strict_agent = Agent(
    name="Study Buddy (Strict)",
    instructions=strict_instructions,
    model=strict_model,
    model_settings=ModelSettings(temperature=0.0),
    tools=base_tools,
    handoffs=handoffs,
)


def print_topics(topics, profile: StudentProfile):
    print("\nAvailable topics:")
    for i, t in enumerate(topics, 1):
        weak_marker = " [!]" if t["id"] in profile.weak_topics else ""
        stats = profile.answered.get(t["id"], {"correct": 0, "total": 0})
        if stats["total"] > 0:
            acc = stats["correct"] / stats["total"]
            acc_str = f" ({acc:.0%} acc)"
        else:
            acc_str = ""
        print(f"  {i}. {t['title']} (ID: {t['id']}){weak_marker}{acc_str}")


def pick_topic(topics, profile: StudentProfile) -> str | None:
    print_topics(topics, profile)
    weak_ids = [tid for tid in profile.weak_topics if any(t["id"] == tid for t in topics)]
    if weak_ids:
        print(f"\nWeak topics: {', '.join(get_topic_title(tid) for tid in weak_ids)}")
        print("Press Enter to let tutor pick a weak topic, or enter topic number/ID:")
    else:
        print("\nEnter topic number/ID (or 'q' to quit):")

    choice = input("> ").strip()
    if choice.lower() == "q":
        return None
    if choice == "":
        if weak_ids:
            return weak_ids[0]
        return None
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(topics):
            return topics[idx]["id"]
    for t in topics:
        if t["id"] == choice:
            return choice
    print("Invalid choice.")
    return pick_topic(topics, profile)


async def run_quiz(agent: Agent, profile: StudentProfile, topic_id: str) -> bool:
    topics = load_topics()
    topic = next(t for t in topics if t["id"] == topic_id)

    print(f"\n=== Topic: {topic['title']} ===")

    # TURN 1: Main tutor asks quiz question
    q_result = await Runner.run(
        question_writer,
        f"Topic: {topic['title']} (ID: {topic_id}). Student level: {profile.level}. Write one quiz question.",
    )
    question = q_result.final_output
    print(f"\n[Turn 1] Agent: {agent.name}")
    print(f"Q: {question}")

    answer = input("\nYour answer: ").strip()
    if answer.lower() == "q":
        return False

    grade_result = await Runner.run(
        grader,
        f"Question: {question}\nStudent answer: {answer}\nKey facts: {topic['key_facts']}",
    )

    print(f"[DEBUG] Raw grader output: {repr(grade_result.final_output)}")
    print(f"[DEBUG] Grader usage: {grade_result.context_wrapper.usage if grade_result.context_wrapper else 'N/A'}")

    try:
        # Try to extract JSON from markdown code blocks
        output = grade_result.final_output.strip()
        if not output:
            print("[DEBUG] Empty output from grader")
            verdict = "incorrect"
            feedback = "Empty grader response"
        elif output.startswith("```"):
            output = output.split("```")[1]
            if output.startswith("json"):
                output = output[4:]
            grade_data = json.loads(output.strip())
            verdict = grade_data.get("verdict", "incorrect")
            feedback = grade_data.get("feedback", "")
        else:
            grade_data = json.loads(output.strip())
            verdict = grade_data.get("verdict", "incorrect")
            feedback = grade_data.get("feedback", "")
    except Exception as e:
        print(f"[DEBUG] Parse error: {e}")
        verdict = "incorrect"
        feedback = "Could not parse grade."

    print(f"\nVerdict: {verdict}")
    if feedback:
        print(f"Feedback: {feedback}")

    was_correct = verdict == "correct"
    
    # Record answer
    stats = profile.answered.get(topic_id, {"correct": 0, "total": 0})
    wrong_count = stats["total"] - stats["correct"]
    handoff_hint = ""
    if wrong_count >= 2:
        handoff_hint = f" NOTE: Student already has {wrong_count} wrong answers on this topic. Check handoff rule."
    
    result = await Runner.run(
        agent,
        f"Record answer for topic {topic_id}: {'correct' if was_correct else 'incorrect'}. Current topic ID: {topic_id}.{handoff_hint}",
        context=profile,
    )

    print(f"\n[Turn 1] Last agent: {result.last_agent.name}")

    for item in result.new_items:
        if isinstance(item, HandoffCallItem):
            tool_call = item.raw_item
            print(f"  [HandoffCallItem] tool={tool_call.name} args={tool_call.arguments}")
        elif isinstance(item, HandoffOutputItem):
            print(f"  [HandoffOutputItem] from={item.source_agent.name} to={item.target_agent.name}")

    # Check if handoff occurred
    if result.last_agent.name == "Remedial Tutor":
        # TURN 2: Remedial Tutor explains with worked example (preserves context via to_input_list)
        print(f"\n--- Remedial explanation ---")
        result = await Runner.run(
            result.last_agent,
            result.to_input_list() + [{"role": "user", "content": "Explain this topic from first principles with a worked example."}],
        )
        print(f"\n[Turn 2] Agent: {result.last_agent.name}")
        print(result.final_output)

        # TURN 3: Remedial Tutor asks check question
        result = await Runner.run(
            result.last_agent,
            result.to_input_list() + [{"role": "user", "content": "Now give me one check question to test my understanding. No grading, just the question."}],
        )
        print(f"\n[Turn 3] Agent: {result.last_agent.name}")
        print(f"Check Q: {result.final_output}")

        check_answer = input("\nYour answer: ").strip()
        if check_answer.lower() == "q":
            return False

        # TURN 4: Grade check question, if correct route back to main tutor
        check_grade = await Runner.run(
            grader,
            f"Question: {result.final_output}\nStudent answer: {check_answer}\nKey facts: {topic['key_facts']}",
        )
        try:
            check_data = json.loads(check_grade.final_output)
            check_verdict = check_data.get("verdict", "incorrect")
        except:
            check_verdict = "incorrect"

        print(f"\nCheck Verdict: {check_verdict}")

        if check_verdict == "correct":
            print(f"\n--- Routing back to {agent.name} for fresh quiz ---")
            result = await Runner.run(
                agent,
                result.to_input_list() + [{"role": "user", "content": f"Student passed check question. Give a fresh quiz question on topic {topic_id}."}],
                context=profile,
            )
            print(f"\n[Turn 4] Agent: {result.last_agent.name}")
            print(f"Fresh Q: {result.final_output}")
        else:
            print(f"\n[Turn 4] Agent: {result.last_agent.name} (remedial continues)")

    return True


def print_summary(profile: StudentProfile):
    print("\n" + "=" * 50)
    print("SESSION SUMMARY")
    print("=" * 50)
    topics = load_topics()
    total_correct = 0
    total_answered = 0
    for tid, stats in profile.answered.items():
        if stats["total"] > 0:
            title = get_topic_title(tid)
            acc = stats["correct"] / stats["total"]
            print(f"  {title}: {stats['correct']}/{stats['total']} ({acc:.0%})")
            total_correct += stats["correct"]
            total_answered += stats["total"]
    if total_answered > 0:
        print(f"\nOverall: {total_correct}/{total_answered} ({total_correct/total_answered:.0%})")
    print(f"Weak topics: {', '.join(get_topic_title(t) for t in profile.weak_topics) or 'none'}")
    print("=" * 50)


async def main():
    existing = load_profile()
    if existing:
        print(f"Welcome back, {existing.name}!")
        name = input(f"Name [{existing.name}]: ").strip() or existing.name
        level = input(f"Level (beginner/intermediate/advanced) [{existing.level}]: ").strip() or existing.level
        profile = StudentProfile(name=name, level=level, weak_topics=existing.weak_topics, answered=existing.answered)
    else:
        name = input("Enter your name: ").strip() or "Student"
        level = input("Level (beginner/intermediate/advanced): ").strip() or "beginner"
        profile = StudentProfile(name=name, level=level)

    topics = load_topics()

    print("\nChoose tutor mode:")
    print("  1. Balanced (default)")
    print("  2. Gentle")
    print("  3. Strict")
    mode = input("> ").strip()
    if mode == "2":
        current_agent = gentle_agent
    elif mode == "3":
        current_agent = strict_agent
    else:
        current_agent = agent

    print(f"\nStarting session with {current_agent.name}. Type 'q' anytime to quit.")

    with trace("Study session"):
        while True:
            topic_id = pick_topic(topics, profile)
            if topic_id is None:
                break
            continue_session = await run_quiz(current_agent, profile, topic_id)
            if not continue_session:
                break
            save_profile(profile)

    print_summary(profile)
    save_profile(profile)
    print(f"\nProgress saved to {PROFILE_FILE}")


async def demo_tool_gating():
    """Demo: run same question as beginner vs intermediate to show tool gating."""
    print("\n" + "=" * 60)
    print("TOOL GATING DEMO")
    print("=" * 60)
    
    for level in ["beginner", "intermediate"]:
        print(f"\n--- Profile level: {level} ---")
        profile = StudentProfile(name="Demo", level=level)
        
        # Create a fresh agent with the same tools to inspect what's available
        test_agent = Agent(
            name="Test Agent",
            instructions="You are a tutor. List available tools.",
            model=model,
            tools=base_tools,
        )
        
        try:
            # Run with low max_turns to see tool offering
            result = await Runner.run(
                test_agent,
                "What tools do you have available?",
                context=profile,
                max_turns=2,
            )
            
            # Check which tools were actually offered/called
            tool_calls = [item for item in result.new_items if hasattr(item, 'tool_call')]
            print(f"  Tools called: {[tc.tool_call.name for tc in tool_calls] if tool_calls else 'none'}")
            
            # Inspect the model's tool schema (what was offered)
            offered = []
            for tool in test_agent.tools:
                offered.append(tool.name if hasattr(tool, 'name') else str(tool))
            
            print(f"  Registered tools: {offered}")
            print(f"  start_exam_mode is_enabled for {level}: {level == 'intermediate'}")
            
        except MaxTurnsExceeded as e:
            print(f"  MaxTurnsExceeded: {e}")
        except Exception as e:
            # StopAtTools is raised as a regular exception with the message
            if "StopAtTools" in str(type(e)) or "Session ended" in str(e):
                print(f"  StopAtTools caught: {e}")
            else:
                print(f"  Error: {type(e).__name__}: {e}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        asyncio.run(demo_tool_gating())
    else:
        asyncio.run(main())