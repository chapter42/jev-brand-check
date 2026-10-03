"""Check per prompt answer whether a brand is mentioned and recommended, using TypeSafe Jev.

A whole-word regex pre-filter skips answers that don't contain the brand, so only
answers that name it are sent to Jev.
"""

import asyncio
import csv
import io
import re

from typesafe_sdk import Noul, NoulCriteria, TypeSafeAuthenticationError, TypeSafeError

QUESTIONS = {
    "mentioned": Noul(
        instructions="Is the brand `brand` mentioned anywhere in `answer`?",
        criteria=NoulCriteria(
            true="The brand, or one of its products or services, is named in the answer, in any context.",
            false="The brand is not named in the answer.",
        ),
    ),
    "recommended": Noul(
        instructions="Does `answer` recommend the brand `brand` to the reader?",
        criteria=NoulCriteria(
            true=(
                "The answer suggests, advises, ranks or lists the brand (or its product or service) "
                "as a good option for what the user is looking for."
            ),
            false=(
                "The brand is not named, is only mentioned neutrally as context, is compared "
                "unfavourably, or is advised against."
            ),
        ),
    ),
}

RESULT_COLUMNS = ["jev_sent", "jev_mentioned_p", "jev_recommended_p", "jev_mentioned", "jev_recommended", "jev_error"]


def read_csv(data):
    """Parse CSV bytes or text; returns (columns, rows, delimiter). The delimiter is sniffed."""
    text = data.decode("utf-8-sig") if isinstance(data, bytes) else data
    try:
        delimiter = csv.Sniffer().sniff(text[:64_000], delimiters=",;\t|").delimiter
    except csv.Error:
        delimiter = ","
    reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=delimiter)
    return reader.fieldnames or [], list(reader), delimiter


def parse_spellings(text):
    """Split comma-separated brand spellings; the first one is the brand name shown to Jev."""
    return [name.strip() for name in text.split(",") if name.strip()]


def build_pattern(spellings):
    # Whole-word match on any spelling, so "nova" doesn't hit "innovatie"; lookarounds instead of \b
    # so names that start or end with punctuation (A&B, nova.nl) still match.
    alternatives = "|".join(re.escape(name) for name in sorted(spellings, key=len, reverse=True))
    return re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)", re.IGNORECASE)


async def judge_rows(client, rows, brand, pattern, column, concurrency, on_progress=None):
    """Judge every row; raises TypeSafeAuthenticationError on the first rejected key."""
    semaphore = asyncio.Semaphore(concurrency)
    done = 0

    async def judge(row):
        nonlocal done
        answer = (row.get(column) or "").strip()
        if not answer:
            result = {"error": "empty answer"}
        elif not pattern.search(answer):
            result = {"mentioned": 0.0, "recommended": 0.0, "sent": False}
        else:
            async with semaphore:
                try:
                    response = await client.system_one(
                        state={"brand": brand, "answer": answer},
                        questions=QUESTIONS,
                    )
                    result = {key: response.nouls[key].noul for key in QUESTIONS} | {"sent": True}
                except TypeSafeAuthenticationError:
                    raise  # an invalid key fails every row, so stop the whole run
                except TypeSafeError as error:
                    result = {"error": f"{type(error).__name__}: {error}"}
        done += 1
        if on_progress:
            on_progress(done, len(rows))
        return result

    # TaskGroup cancels the remaining rows as soon as one task raises.
    try:
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(judge(row)) for row in rows]
    except* TypeSafeAuthenticationError as errors:
        raise errors.exceptions[0] from None
    return [task.result() for task in tasks]


def annotate(rows, results, threshold):
    """Return copies of rows with the RESULT_COLUMNS filled in."""
    annotated = []
    for row, result in zip(rows, results):
        mentioned = result.get("mentioned")
        recommended = result.get("recommended")
        sent = result.get("sent")
        annotated.append(row | {
            "jev_sent": "" if sent is None else ("yes" if sent else "no (brand not in text)"),
            "jev_mentioned_p": "" if not sent else f"{mentioned:.3f}",
            "jev_recommended_p": "" if not sent else f"{recommended:.3f}",
            "jev_mentioned": "" if mentioned is None else ("yes" if mentioned >= threshold else "no"),
            "jev_recommended": "" if recommended is None else ("yes" if recommended >= threshold else "no"),
            "jev_error": result.get("error", ""),
        })
    return annotated


def summarize(results, threshold):
    judged = [r for r in results if "error" not in r]
    return {
        "judged": len(judged),
        "errors": len(results) - len(judged),
        "sent": sum(r["sent"] for r in judged),
        "mentioned": sum(r["mentioned"] >= threshold for r in judged),
        "recommended": sum(r["recommended"] >= threshold for r in judged),
        "unsure": sum(abs(r["recommended"] - 0.5) < 0.2 for r in judged),
    }


def to_csv(columns, rows, delimiter):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=columns + RESULT_COLUMNS, delimiter=delimiter)
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()
