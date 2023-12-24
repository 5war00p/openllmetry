"""OpenTelemetry Vertex AI instrumentation"""
import logging
import os
import types
from typing import Collection
from wrapt import wrap_function_wrapper

from opentelemetry import context as context_api
from opentelemetry.trace import get_tracer, SpanKind
from opentelemetry.trace.status import Status, StatusCode

from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import (
    _SUPPRESS_INSTRUMENTATION_KEY,
    unwrap
)

from opentelemetry.semconv.ai import SpanAttributes, LLMRequestTypeValues
from opentelemetry.instrumentation.vertexai.version import __version__

from vertexai.generative_models._generative_models import Part

logger = logging.getLogger(__name__)

_instruments = ("google-cloud-aiplatform",)

WRAPPED_METHODS = [
    {
        "package": "vertexai.preview.generative_models",
        "object": "GenerativeModel",
        "method": "generate_content",
        "span_name": "vertexai.generate_content",
    },
    {
        "package": "vertexai.language_models",
        "object": "TextGenerationModel",
        "method": "predict",
        "span_name": "vertexai.predict",
    },
    {
        "package": "vertexai.language_models",
        "object": "TextGenerationModel",
        "method": "predict_async",
        "span_name": "vertexai.predict",
    },
    {
        "package": "vertexai.language_models",
        "object": "TextGenerationModel",
        "method": "predict_streaming",
        "span_name": "vertexai.predict",
    },
    {
        "package": "vertexai.language_models",
        "object": "TextGenerationModel",
        "method": "predict_streaming_async",
        "span_name": "vertexai.predict",
    },
]


def should_send_prompts():
    return (
        os.getenv("TRACELOOP_TRACE_CONTENT") or "true"
    ).lower() == "true" or context_api.get_value("override_enable_content_tracing")


def is_streaming_response(response):
    return isinstance(response, types.GeneratorType)


def _set_span_attribute(span, name, value):
    if value is not None:
        if value != "":
            span.set_attribute(name, value)
    return

input_attribute_map = {
    "prompt": f"{SpanAttributes.LLM_PROMPTS}.0.user",
    "max_output_tokens": SpanAttributes.LLM_REQUEST_MAX_TOKENS,
    "temperature": SpanAttributes.LLM_TEMPERATURE,
    "top_p": SpanAttributes.LLM_TOP_P,
    "presence_penalty": SpanAttributes.LLM_PRESENCE_PENALTY,
    "frequency_penalty": SpanAttributes.LLM_FREQUENCY_PENALTY
}


def _set_input_attributes(span, args, kwargs):

    if (should_send_prompts() and args is not None and len(args) > 0):
        prompt = ''
        for arg in args:
            if isinstance(arg, str):
                prompt = f"{prompt}{arg}\n"
            elif isinstance(arg, list):
                for subarg in arg:
                    if isinstance(subarg, str):
                        prompt = f"{prompt}{subarg}\n"
                    # Gemini
                    elif isinstance(subarg, Part):
                        if hasattr(subarg, 'text'):
                            prompt = f"{prompt}text: {subarg.text.file_uri}\n"
                        elif hasattr(subarg, 'mime_type'):
                            prompt = f"{prompt}mime_type: {subarg.mime_type}\n"
                        elif hasattr(subarg, 'inline_data'):
                            prompt = f"{prompt}data: {subarg.inline_data.data}\nmime_type: {subarg.inline_data.mime_type}\n"
                        elif hasattr(subarg, 'file_data'):
                            prompt = f"{prompt}file_uri: {subarg.file_data.file_uri}\nmime_type: {subarg.file_data.mime_type}\n"

        _set_span_attribute(
            span,
            input_attribute_map.get("prompt"),
            prompt,
        )

    _set_span_attribute(span, SpanAttributes.LLM_TEMPERATURE, kwargs.get('temperature'))
    _set_span_attribute(span, SpanAttributes.LLM_REQUEST_MAX_TOKENS, kwargs.get('max_output_tokens'))
    _set_span_attribute(span, SpanAttributes.LLM_TOP_P, kwargs.get('top_p'))
    _set_span_attribute(span, SpanAttributes.LLM_PRESENCE_PENALTY, kwargs.get('presence_penalty'))
    _set_span_attribute(span, SpanAttributes.LLM_FREQUENCY_PENALTY, kwargs.get('frequency_penalty'))

    return

def is_streaming_response(response):
    return isinstance(response, types.GeneratorType) or isinstance(response, types.AsyncGeneratorType)

def _set_response_attributes(span, response):
    if hasattr(response, 'text'):
        if hasattr(response, '_raw_response') and hasattr(response._raw_response, 'usage_metadata'):
            _set_span_attribute(
                span, SpanAttributes.LLM_USAGE_TOTAL_TOKENS, response._raw_response.usage_metadata.total_token_count
            )
            _set_span_attribute(
                span, SpanAttributes.LLM_USAGE_COMPLETION_TOKENS, response._raw_response.usage_metadata.candidates_token_count
            )
            _set_span_attribute(
                span, SpanAttributes.LLM_USAGE_PROMPT_TOKENS, response._raw_response.usage_metadata.prompt_token_count
            )


        if isinstance(response.text, list):
            for index, item in enumerate(response):
                prefix = f"{SpanAttributes.LLM_COMPLETIONS}.{index}"
                _set_span_attribute(span, f"{prefix}.content", item.text)
        elif isinstance(response.text, str):
            _set_span_attribute(
                span, f"{SpanAttributes.LLM_COMPLETIONS}.0.content", response.text
            )
    else:
        if isinstance(response, list):
            for index, item in enumerate(response):
                prefix = f"{SpanAttributes.LLM_COMPLETIONS}.{index}"
                _set_span_attribute(span, f"{prefix}.content", item)
        elif isinstance(response, str):
            _set_span_attribute(
                span, f"{SpanAttributes.LLM_COMPLETIONS}.0.content", response
            )

    return

def _build_from_streaming_response(span, response):
    complete_response = ""
    for item in response:
        item_to_yield = item
        complete_response += str(item)

        yield item_to_yield

    _set_response_attributes(span, complete_response)

    span.set_status(Status(StatusCode.OK))
    span.end()

async def _abuild_from_streaming_response(span, response):
    complete_response = ""
    async for item in response:
        item_to_yield = item
        complete_response += str(item)

        yield item_to_yield

    _set_response_attributes(span, complete_response)

    span.set_status(Status(StatusCode.OK))
    span.end()

def _handle_request(span, args, kwargs):
    try:
        if span.is_recording():
            _set_input_attributes(span, args, kwargs)

    except Exception as ex:  # pylint: disable=broad-except
        logger.warning(
            "Failed to set input attributes for VertexAI span, error: %s", str(ex)
        )

def _handle_response(span, response):
    try:
        if span.is_recording():
            _set_response_attributes(span, response)

    except Exception as ex:  # pylint: disable=broad-except
        logger.warning(
            "Failed to set response attributes for VertexAI span, error: %s",
            str(ex),
        )
    if span.is_recording():
        span.set_status(Status(StatusCode.OK))


def _with_tracer_wrapper(func):
    """Helper for providing tracer for wrapper functions."""

    def _with_tracer(tracer, to_wrap):
        def wrapper(wrapped, instance, args, kwargs):
            return func(tracer, to_wrap, wrapped, instance, args, kwargs)

        return wrapper

    return _with_tracer


@_with_tracer_wrapper
async def _awrap(tracer, to_wrap, wrapped, instance, args, kwargs):
    if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
        return await wrapped(*args, **kwargs)

    name = to_wrap.get("span_name")
    span = tracer.start_span(
        name,
        kind=SpanKind.CLIENT,
        attributes={
            SpanAttributes.LLM_VENDOR: "VertexAI",
            SpanAttributes.LLM_REQUEST_TYPE: LLMRequestTypeValues.COMPLETION.value,
        },
    )

    _handle_request(span, args, kwargs)

    response = await wrapped(*args, **kwargs)

    if response:
        if is_streaming_response(response):
            # span will be closed after the generator is done
            return _abuild_from_streaming_response(span, response)
        else:
            _handle_response(span, response)

    span.end()

    return response

@_with_tracer_wrapper
def _wrap(tracer, to_wrap, wrapped, instance, args, kwargs):

    """Instruments and calls every function defined in TO_WRAP."""
    if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
        return wrapped(*args, **kwargs)

    name = to_wrap.get("span_name")
    span = tracer.start_span(
        name,
        kind=SpanKind.CLIENT,
        attributes={
            SpanAttributes.LLM_VENDOR: "VertexAI",
            SpanAttributes.LLM_REQUEST_TYPE: LLMRequestTypeValues.COMPLETION.value,
        },
    )

    _handle_request(span, args, kwargs)

    response = wrapped(*args, **kwargs)

    if response:
        if is_streaming_response(response):
            return _build_from_streaming_response(span, response)
        else:
            _handle_response(span, response)

    span.end()
    return response


class VertexAIInstrumentor(BaseInstrumentor):
    """An instrumentor for VertextAI's client library."""

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        tracer_provider = kwargs.get("tracer_provider")
        tracer = get_tracer(__name__, __version__, tracer_provider)
        for wrapped_method in WRAPPED_METHODS:
            wrap_package = wrapped_method.get("package")
            wrap_object = wrapped_method.get("object")
            wrap_method = wrapped_method.get("method")

            wrap_function_wrapper(
                wrap_package,
                f"{wrap_object}.{wrap_method}",
                _awrap(tracer, wrapped_method) if wrap_method.endswith('_async') else _wrap(tracer, wrapped_method),
            )

    def _uninstrument(self, **kwargs):
        for wrapped_method in WRAPPED_METHODS:
            wrap_package = wrapped_method.get("package")
            wrap_object = wrapped_method.get("object")
            unwrap(
                f"{wrap_package}.{wrap_object}",
                wrapped_method.get("method", ""),
            )
