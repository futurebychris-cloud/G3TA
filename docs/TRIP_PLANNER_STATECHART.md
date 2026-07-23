# G3TA Trip Planner State Chart

This chart documents the current trip-planning experience. It uses the same
node convention as the reference JSON:

- Type `1`: interactive instruction or user decision
- Type `2`: message, recovery, or result
- Type `3`: function/action

The chart ends when the planned trip is ready. Booking is a separate workflow
and is intentionally not included.

```mermaid
flowchart TD
    START([0 · Welcome to G3TA])
    FORM["1 · Collect or review trip brief<br/>Type 1"]
    VALIDATE["2 · Validate trip input<br/>Type 3 · validate_trip_input"]
    PREPARE["3 · Create planning session<br/>Type 3 · prepare_trip_input"]
    BUDGET["4 · Budget Agent<br/>Type 3 · run_single_agent"]
    SPECIALISTS["5 · Run five specialists concurrently<br/>Transportation · Housing · Food<br/>Activity · Planning"]
    GEO["6 · Destination safety check<br/>Type 3 · validate_agent_geography"]
    SYNTH["7 · Reconcile and synthesize<br/>Type 3 · reconcile_and_synthesize"]
    READY(["8 · Planned trip ready<br/>Itinerary · Map · Budget · Packing<br/>Weather · Agent reasoning"])

    VOICE_INTRO["20 · Explain voice-guided setup<br/>Type 2"]
    VOICE_QUESTION["21 · Ask one trip question<br/>Voice or typed answer · Type 1"]
    VOICE_CAPTURE["22 · Store current answer<br/>Type 3 · capture_guided_answer"]
    VOICE_PARSE["23 · Normalize all answers<br/>Type 3 · parse_intake"]
    VOICE_REVIEW["24 · Review accessible draft<br/>Type 1"]

    INPUT_ERROR["90 · Trip brief needs correction"]
    SESSION_ERROR["91 · Session creation failed"]
    BUDGET_ERROR["92 · Budget Agent failed"]
    AGENT_ERROR["93 · Specialist Agent failed"]
    GEO_ERROR["94 · Destination data inconsistent"]
    SYNTH_ERROR["95 · Synthesis failed"]
    VOICE_UNAVAILABLE["96 · Voice unavailable<br/>Continue by typing"]
    VOICE_MISSING["97 · Required answer missing<br/>Repeat only that question"]
    VOICE_ERROR["98 · Guided answers could not be parsed"]

    START -->|Standard trip brief| FORM
    START -->|Voice-guided setup| VOICE_INTRO
    FORM -->|Submit| VALIDATE
    FORM -->|Switch to voice| VOICE_INTRO

    VALIDATE -->|Valid| PREPARE
    VALIDATE -->|Invalid| INPUT_ERROR
    INPUT_ERROR -->|Correct fields| FORM

    PREPARE -->|Ready| BUDGET
    PREPARE -->|Failed| SESSION_ERROR
    SESSION_ERROR -->|Retry| PREPARE
    SESSION_ERROR -->|Edit brief| FORM

    BUDGET -->|Completed| SPECIALISTS
    BUDGET -->|Failed| BUDGET_ERROR
    BUDGET_ERROR -->|Retry| BUDGET
    BUDGET_ERROR -->|Edit brief| FORM

    SPECIALISTS -->|All completed| GEO
    SPECIALISTS -->|One failed| AGENT_ERROR
    AGENT_ERROR -->|Retry specialists| SPECIALISTS
    AGENT_ERROR -->|Edit brief| FORM

    GEO -->|Destination correct| SYNTH
    GEO -->|Mixed-city data| GEO_ERROR
    GEO_ERROR -->|Clean retry| SPECIALISTS
    GEO_ERROR -->|Edit brief| FORM

    SYNTH -->|Itinerary valid| READY
    SYNTH -->|Could not combine| SYNTH_ERROR
    SYNTH_ERROR -->|Retry synthesis| SYNTH
    SYNTH_ERROR -->|Edit brief| FORM

    VOICE_INTRO -->|Start| VOICE_QUESTION
    VOICE_INTRO -->|Close| START
    VOICE_QUESTION -->|Answer| VOICE_CAPTURE
    VOICE_QUESTION -->|Voice unavailable| VOICE_UNAVAILABLE
    VOICE_UNAVAILABLE -->|Type instead| VOICE_QUESTION
    VOICE_CAPTURE -->|More questions| VOICE_QUESTION
    VOICE_CAPTURE -->|All answered| VOICE_PARSE
    VOICE_PARSE -->|Complete| VOICE_REVIEW
    VOICE_PARSE -->|Missing required answer| VOICE_MISSING
    VOICE_PARSE -->|Parse failed| VOICE_ERROR
    VOICE_MISSING -->|Repeat missing question| VOICE_QUESTION
    VOICE_ERROR -->|Retry review| VOICE_PARSE
    VOICE_ERROR -->|Edit answer| VOICE_QUESTION
    VOICE_REVIEW -->|Fill main form| FORM
    VOICE_REVIEW -->|Edit answer| VOICE_QUESTION

    classDef entry fill:#0a2034,color:#fff,stroke:#0a2034,stroke-width:2px;
    classDef action fill:#dff3ff,color:#0a2034,stroke:#0a2034;
    classDef decision fill:#eef9c8,color:#0a2034,stroke:#0a2034;
    classDef recovery fill:#fff0cc,color:#0a2034,stroke:#d48324;
    classDef final fill:#cef26f,color:#0a2034,stroke:#0a2034,stroke-width:3px;

    class START entry;
    class VALIDATE,PREPARE,BUDGET,SPECIALISTS,GEO,SYNTH,VOICE_CAPTURE,VOICE_PARSE action;
    class FORM,VOICE_QUESTION,VOICE_REVIEW decision;
    class INPUT_ERROR,SESSION_ERROR,BUDGET_ERROR,AGENT_ERROR,GEO_ERROR,SYNTH_ERROR,VOICE_UNAVAILABLE,VOICE_MISSING,VOICE_ERROR recovery;
    class READY final;
```

## Main success path

`Trip brief → validation → planning session → Budget Agent → five parallel
specialists → destination check → reconciliation and synthesis → planned trip`

## Source files

- Machine-readable chart: [`trip_planner_statechart.json`](../trip_planner_statechart.json)
- Validated state-machine reader: [`backend/state_machine.py`](../backend/state_machine.py)
- Contract tests: [`backend/tests/test_state_machine.py`](../backend/tests/test_state_machine.py)
