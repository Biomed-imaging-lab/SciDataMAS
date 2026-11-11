"""ProbeAgent: runs one open-ended probing session per (run, probe).

The probe mentally walks through its task's procedure and asks questions
until it decides it has enough (bounded by [MIN_QUESTIONS, MAX_QUESTIONS],
enforced in code, not by the LLM). No metadata or retriever ever reaches the
question-generation call — structurally enforced by that call's signature.

Context moderation: at judge time the probe sees the FULL candidate-field
list (all top-K, verbatim content) to decide relevance. Once judged, only the
fields it named as `good_fields` are kept in the running transcript for
subsequent turns — everything else from that candidate list is dropped. This
stops the probe from silently accumulating knowledge of sibling/adjacent
field names across a long session (a session-scale variant of the same
info-asymmetry concern the blind ask() already guards against).
"""

import sys
from pathlib import Path
from typing import List, Optional, Tuple, TypedDict

from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from cache import cached_call
from data_contracts import QuestionRecord, SessionMeta
from roster import ProbeConfig

Transcript = List[Tuple[str, str]]  # (role, content) pairs, role in {"assistant", "user"}


class AskOrStop(BaseModel):
    continue_probing: bool = Field(description="True to ask another question, False if you have what you need")
    question: Optional[str] = Field(default=None, description="Your single next question, required if continue_probing is True")


class ProbeVerdict(BaseModel):
    question_valid: bool = Field(description="Was this a reasonable question to ask about this dataset")
    sufficient: bool = Field(description="Do the candidate fields sufficiently answer the question")
    good_fields: List[str] = Field(default=[], description="Candidate field names that were genuinely useful")
    reason: str = Field(default="", description="Short justification")


class AskState(TypedDict):
    system_prompt: str
    messages: Transcript
    turn_text: str
    result: AskOrStop


class JudgeState(TypedDict):
    system_prompt: str
    messages: Transcript
    turn_text: str
    result: ProbeVerdict


def _render_candidate(name: str, field) -> str:
    return f" - {name}: {field}"


class ProbeAgent:
    def __init__(self, probe: ProbeConfig):
        self.probe = probe

        self._session_prompt_template = config.PROBE_SESSION_PROMPT_PATH.read_text()
        self._ask_turn_template = config.PROBE_ASK_TURN_PROMPT_PATH.read_text()
        self._judge_turn_template = config.PROBE_JUDGE_TURN_PROMPT_PATH.read_text()

        ask_llm = init_chat_model(
            config.PROBE_MODEL, model_provider=config.PROBE_PROVIDER, temperature=config.ASK_TEMPERATURE
        )
        judge_llm = init_chat_model(
            config.PROBE_MODEL, model_provider=config.PROBE_PROVIDER, temperature=config.JUDGE_TEMPERATURE
        )
        self._ask_llm_chain = ask_llm.with_structured_output(AskOrStop, method="json_schema", strict=False)
        self._judge_llm_chain = judge_llm.with_structured_output(
            ProbeVerdict, method="json_schema", strict=False
        )

        self.ask_workflow = self._build_workflow(AskState, self._ask_node)
        self.judge_workflow = self._build_workflow(JudgeState, self._judge_node)

    def _build_workflow(self, state_cls, node_fn):
        workflow = StateGraph(state_cls)
        workflow.add_node("step", node_fn)
        workflow.add_edge(START, "step")
        workflow.add_edge("step", END)
        return workflow.compile()

    def _ask_node(self, state: AskState) -> AskState:
        def _call():
            chat = ChatPromptTemplate.from_messages(
                [("system", state["system_prompt"]), ("placeholder", "{messages}")], "f-string"
            )
            chain = chat | self._ask_llm_chain
            return chain.invoke({"messages": state["messages"] + [("user", state["turn_text"])]})

        state["result"] = cached_call(
            model=f"{config.PROBE_MODEL}:ask:{config.ASK_TEMPERATURE}",
            payload={"system_prompt": state["system_prompt"], "messages": state["messages"], "turn_text": state["turn_text"]},
            fn=_call,
            to_dict=lambda r: r.model_dump(),
            from_dict=lambda d: AskOrStop(**d),
        )
        return state

    def _judge_node(self, state: JudgeState) -> JudgeState:
        def _call():
            chat = ChatPromptTemplate.from_messages(
                [("system", state["system_prompt"]), ("placeholder", "{messages}")], "f-string"
            )
            chain = chat | self._judge_llm_chain
            return chain.invoke({"messages": state["messages"] + [("user", state["turn_text"])]})

        state["result"] = cached_call(
            model=f"{config.PROBE_MODEL}:judge:{config.JUDGE_TEMPERATURE}",
            payload={"system_prompt": state["system_prompt"], "messages": state["messages"], "turn_text": state["turn_text"]},
            fn=_call,
            to_dict=lambda r: r.model_dump(),
            from_dict=lambda d: ProbeVerdict(**d),
        )
        return state

    def _session_prompt(self, scenario_context: str) -> str:
        return self._session_prompt_template.format(
            role_label=self.probe.role_label,
            task_scenario=self.probe.task_scenario,
            scenario_context=scenario_context,
        )

    def _ask_or_stop(
        self, system_prompt: str, transcript: Transcript, question_num: int, force_retry: bool = False
    ) -> AskOrStop:
        if question_num < config.MIN_QUESTIONS:
            stop_option_text = "You must ask another question now — you have not reached the minimum yet."
            if force_retry:
                stop_option_text += (
                    " Your previous response did not include a question even though you are "
                    "still below the minimum — you MUST provide one this time."
                )
        else:
            stop_option_text = (
                "You may either ask another question, or declare you have enough "
                "information and stop (set continue_probing to false)."
            )
        turn_text = self._ask_turn_template.format(
            question_num=question_num,
            min_questions=config.MIN_QUESTIONS,
            max_questions=config.MAX_QUESTIONS,
            stop_option_text=stop_option_text,
        )
        state: AskState = {
            "system_prompt": system_prompt,
            "messages": transcript,
            "turn_text": turn_text,
            "result": None,
        }
        return self.ask_workflow.invoke(state)["result"]

    def _judge(
        self, system_prompt: str, transcript: Transcript, question: str, candidate_fields: List[str], retriever
    ) -> ProbeVerdict:
        if not candidate_fields:
            return ProbeVerdict(
                question_valid=True, sufficient=False, good_fields=[], reason="no candidate fields retrieved"
            )
        candidate_text = "\n".join(
            _render_candidate(name, retriever.field_view(name)) for name in candidate_fields
        )
        turn_text = self._judge_turn_template.format(question=question, candidate_fields=candidate_text)
        state: JudgeState = {
            "system_prompt": system_prompt,
            "messages": transcript,
            "turn_text": turn_text,
            "result": None,
        }
        return self.judge_workflow.invoke(state)["result"]

    def run_session(self, run_id: int, scenario_context: str, retriever, target_key: str, logger=None):
        """Runs one open-ended session, yielding (QuestionRecord, is_last) pairs
        so the caller can persist incrementally without buffering the session."""
        system_prompt = self._session_prompt(scenario_context)
        transcript: Transcript = []
        session_q_idx = 0

        while True:
            ask_result = self._ask_or_stop(system_prompt, transcript, session_q_idx)

            if session_q_idx < config.MIN_QUESTIONS and (not ask_result.continue_probing or not ask_result.question):
                # model ignored the "you must ask" instruction below MIN_QUESTIONS; retry once
                if logger:
                    logger.warning(
                        f"run{run_id} {self.probe.id}: model tried to stop before MIN_QUESTIONS "
                        f"at q{session_q_idx}, retrying the ask turn"
                    )
                ask_result = self._ask_or_stop(system_prompt, transcript, session_q_idx, force_retry=True)

            if not ask_result.continue_probing and session_q_idx >= config.MIN_QUESTIONS:
                stop_reason = "probe_decided"
                break
            if session_q_idx >= config.MAX_QUESTIONS:
                stop_reason = "max_reached"
                break
            if not ask_result.question:
                # still no usable question after the retry (below MIN) or the
                # model said continue=True but left question empty — end the
                # session rather than inject a synthetic filler question.
                if logger:
                    logger.warning(
                        f"run{run_id} {self.probe.id}: no question produced at q{session_q_idx}, ending session early"
                    )
                stop_reason = "probe_decided"
                break

            question = ask_result.question
            field_scores = retriever.score(question)
            candidates = retriever.candidates(field_scores)
            verdict = self._judge(system_prompt, transcript, question, candidates, retriever)

            record = QuestionRecord(
                run_id=run_id,
                session_q_idx=session_q_idx,
                probe_id=self.probe.id,
                probe_mode=self.probe.mode,
                question=question,
                question_valid=verdict.question_valid,
                field_scores=field_scores,
                candidate_fields=candidates,
                sufficient=verdict.sufficient,
                good_fields=verdict.good_fields,
                reason=verdict.reason,
                target_key=target_key,
                model_probe=config.PROBE_MODEL,
                embedding_model=config.EMBEDDING_MODEL,
            )

            # context moderation: show full candidates only for judging; keep
            # only good_fields (or a "nothing useful" note) in the transcript
            # going forward.
            transcript.append(("assistant", f"Question {session_q_idx + 1}: {question}"))
            if verdict.good_fields:
                kept = "\n".join(
                    _render_candidate(name, retriever.field_view(name))
                    for name in verdict.good_fields
                    if name in candidates
                )
                transcript.append(("user", f"Fields kept from this search (relevant, retained in your view):\n{kept}"))
            else:
                transcript.append(("user", "No fields from this search were useful; nothing retained."))

            if logger:
                logger.debug(
                    f"run{run_id} {self.probe.id} q{session_q_idx} | {question!r} "
                    f"| candidates={candidates} | sufficient={verdict.sufficient} | good={verdict.good_fields}"
                )

            yield record
            session_q_idx += 1

        yield SessionMeta(run_id=run_id, probe_id=self.probe.id, n_questions=session_q_idx, stop_reason=stop_reason)
