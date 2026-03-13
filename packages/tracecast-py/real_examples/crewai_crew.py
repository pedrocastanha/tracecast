import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parents[3] / ".env")
except ImportError:
    pass

from crewai import Agent, Crew, Task
from tracecast import Span, SpanType, Tracer, calculate_cost

logging.basicConfig(level=logging.INFO, format="%(message)s")

tracer = Tracer(logging=True, log_prefix="crewai_manager")

researcher = Agent(
    role="Researcher",
    goal="Research AI market trends",
    backstory="Expert AI researcher with 10 years of experience",
    llm="gpt-4o-mini",
)
writer = Agent(
    role="Writer",
    goal="Write a LinkedIn post about AI trends",
    backstory="Expert content writer specializing in tech",
    llm="gpt-4o-mini",
)

t1 = Task(
    description="Research the top 3 AI trends of 2026",
    expected_output="A list of 3 trends with brief descriptions",
    agent=researcher,
)
t2 = Task(
    description="Write a LinkedIn post summarizing the research",
    expected_output="A LinkedIn post of 3-4 paragraphs",
    agent=writer,
)


def run_crew():
    with tracer.trace("crewai_kickoff", project_id="content_team") as trace:
        crew = Crew(agents=[researcher, writer], tasks=[t1, t2], verbose=False)

        s_t = datetime.now(timezone.utc)
        result = crew.kickoff()
        e_t = datetime.now(timezone.utc)

        usage = getattr(result, "token_usage", None)
        tokens_in = getattr(usage, "prompt_tokens", 0) or 0
        tokens_out = getattr(usage, "completion_tokens", 0) or 0

        span = Span(
            span_id=str(uuid.uuid4()),
            type=SpanType.AGENT,
            name="crewai_sequential",
            model="gpt-4o-mini",
            started_at=s_t,
            finished_at=e_t,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
        span.cost_usd = calculate_cost("gpt-4o-mini", tokens_in, tokens_out)
        trace.spans.append(span)

        return result


if __name__ == "__main__":
    result = run_crew()
    print(f"\nResultado:\n{result}")
