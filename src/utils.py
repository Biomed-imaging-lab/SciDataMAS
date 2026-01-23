import threading
from time import sleep
from typing import Any, Dict, List

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult
import httpx


def invoke(chain, params):
    while True:
        try:
            response = chain.invoke(params)
            return response
        except Exception as e:
            #не ретраим 4xx ошибки.
            if isinstance(e, httpx.HTTPStatusError):
                status = getattr(getattr(e, "response", None), "status_code", None)
                if status is not None:
                    status = int(status)
                    error_unwanted = {400, 401, 402, 403, 404, 409, 413, 422}
                    if status in error_unwanted:
                        raise
            print(f"Can't invoke the chain (err: {str(e)}). Wait 5 secs...")
            sleep(5)


class TokenUsageCallbackCounter(BaseCallbackHandler):
    """Base callback handler that can be used to handle callbacks from langchain."""

    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def __init__(self):
        super().__init__()
        self._lock = threading.Lock()

    def __repr__(self) -> str:
        return (
            f"Tokens Used: {self.total_tokens}\n"
            f"\tPrompt Tokens: {self.prompt_tokens}\n"
            f"\tCompletion Tokens: {self.completion_tokens}\n"
        )

    def on_llm_start(
        self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
    ) -> Any:
        """Run when LLM starts running."""

    def on_llm_new_token(self, token: str, **kwargs: Any) -> Any:
        """Run on new LLM token. Only available when streaming is enabled."""

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> Any:
        """Run when LLM ends running."""

        # Check for usage_metadata (langchain-core >= 0.2.2)
        try:
            generation = response.generations[0][0]
        except IndexError:
            generation = None
        if isinstance(generation, ChatGeneration):
            try:
                message = generation.message
                if isinstance(message, AIMessage):
                    usage_metadata = message.usage_metadata
                else:
                    usage_metadata = None
            except AttributeError:
                usage_metadata = None
        else:
            usage_metadata = None

        if usage_metadata:
            token_usage = {"total_tokens": usage_metadata["total_tokens"]}
            completion_tokens = usage_metadata["output_tokens"]
            prompt_tokens = usage_metadata["input_tokens"]

        else:
            if response.llm_output is None:
                return None

            if "token_usage" not in response.llm_output:
                with self._lock:
                    self.successful_requests += 1
                return None

            # compute tokens and cost for this request
            token_usage = response.llm_output["token_usage"]
            completion_tokens = token_usage.get("completion_tokens", 0)
            prompt_tokens = token_usage.get("prompt_tokens", 0)

        # update shared state behind lock
        with self._lock:
            self.total_tokens += token_usage.get("total_tokens", 0)
            self.prompt_tokens += prompt_tokens
            self.completion_tokens += completion_tokens
