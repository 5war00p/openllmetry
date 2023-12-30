import os
import asyncio
import vertexai
from traceloop.sdk.decorators import workflow, aworkflow
from vertexai.language_models import TextGenerationModel, ChatModel, InputOutputTextPair
from vertexai.preview.generative_models import GenerativeModel, Part

project_id = os.getenv('VERTEXAI_PROJECT_ID')
location = os.getenv('VERTEXAI_LOCATION')

vertexai.init(project=project_id, location=location)


def test_vertexai_generate_content(exporter):
    @workflow("generate_content")
    def generate_text() -> str:
        """Generate content with Multimodal Model (Gemini)"""

        multimodal_model = GenerativeModel("gemini-pro-vision")
        response = multimodal_model.generate_content(
            [
                Part.from_uri(
                    "gs://generativeai-downloads/images/scones.jpg", mime_type="image/jpeg"
                ),
                "what is shown in this image?",
            ]
        )
        return response.text

    generate_text()

    spans = exporter.get_finished_spans()
    print('>>> spans', [span.name for span in spans])
    assert [span.name for span in spans] == [
        "vertexai.generate_content",
        "generate_content.workflow",
    ]

    vertexai_span = spans[0]
    assert (
        "what is shown in this image?" in vertexai_span.attributes["llm.prompts.0.user"]
    )


def test_vertexai_predict(exporter):
    @workflow("predict")
    def predict_text() -> str:
        """Ideation example with a Large Language Model"""

        parameters = {
            "max_output_tokens": 256,
            "top_p": 0.8,
            "top_k": 40,
        }

        model = TextGenerationModel.from_pretrained("text-bison@001")
        response = model.predict(
            "Give me ten interview questions for the role of program manager.",
            **parameters,
        )

        return response.text
    predict_text()

    spans = exporter.get_finished_spans()
    assert [span.name for span in spans] == [
        "vertexai.predict",
        "predict.workflow",
    ]

    vertexai_span = spans[0]
    assert (
        "Give me ten interview questions for the role of program manager." in vertexai_span.attributes["llm.prompts.0.user"]
    )


def test_vertexai_predict_async(exporter):
    @aworkflow("predict_async")
    async def async_predict_text() -> str:
        """Ideation example with a Large Language Model"""

        parameters = {
            "max_output_tokens": 256,
            "top_p": 0.8,
            "top_k": 40,
        }

        model = TextGenerationModel.from_pretrained("text-bison@001")
        response = await model.predict_async(
            "Give me ten interview questions for the role of program manager.",
            **parameters,
        )

        return response.text
    asyncio.run(async_predict_text())

    spans = exporter.get_finished_spans()
    assert [span.name for span in spans] == [
        "vertexai.predict",
        "predict_async.workflow",
    ]

    vertexai_span = spans[0]
    assert (
        "Give me ten interview questions for the role of program manager." in vertexai_span.attributes["llm.prompts.0.user"]
    )


def test_vertexai_stream(exporter):
    @workflow("stream_prediction")
    def streaming_prediction() -> str:
        """Streaming Text Example with a Large Language Model"""

        text_generation_model = TextGenerationModel.from_pretrained("text-bison")
        parameters = {
            "max_output_tokens": 256,
            "top_p": 0.8,
            "top_k": 40,
        }
        responses = text_generation_model.predict_streaming(
            prompt="Give me ten interview questions for the role of program manager.",
            **parameters)

        result = [response for response in responses]
        return result
    streaming_prediction()
    spans = exporter.get_finished_spans()
    assert [span.name for span in spans] == [
        "vertexai.predict",
        "stream_prediction.workflow",
    ]

    vertexai_span = spans[0]
    assert (
        "Give me ten interview questions for the role of program manager." in vertexai_span.attributes["llm.prompts.0.user"]
    )


def test_vertexai_stream_async(exporter):
    @aworkflow("stream_prediction_async")
    async def async_streaming_prediction() -> str:
        """Streaming Text Example with a Large Language Model"""

        text_generation_model = TextGenerationModel.from_pretrained("text-bison")
        parameters = {
            "max_output_tokens": 256,
            "top_p": 0.8,
            "top_k": 40,
        }

        responses = text_generation_model.predict_streaming_async(
            prompt="Give me ten interview questions for the role of program manager.",
            **parameters
        )
        result = [response async for response in responses]
        return result
    asyncio.run(async_streaming_prediction())

    spans = exporter.get_finished_spans()
    assert [span.name for span in spans] == [
        "vertexai.predict",
        "stream_prediction_async.workflow",
    ]

    vertexai_span = spans[0]
    assert (
        "Give me ten interview questions for the role of program manager." in vertexai_span.attributes["llm.prompts.0.user"]
    )

def test_vertexai_chat(exporter):
    @workflow("send_message")
    def chat() -> str:
        """Chat Example with a Large Language Model"""

        chat_model = ChatModel.from_pretrained("chat-bison@001")

        parameters = {
            "max_output_tokens": 256,
            "top_p": 0.95,
            "top_k": 40,
        }

        chat = chat_model.start_chat(
            context="My name is Miles. You are an astronomer, knowledgeable about the solar system.",
            examples=[
                InputOutputTextPair(
                    input_text="How many moons does Mars have?",
                    output_text="The planet Mars has two moons, Phobos and Deimos.",
                ),
            ],
        )

        response = chat.send_message(
            "How many planets are there in the solar system?", **parameters
        )

        return response.text
    chat()

    spans = exporter.get_finished_spans()
    assert [span.name for span in spans] == [
        "vertexai.send_message",
        "send_message.workflow",
    ]

    vertexai_span = spans[0]
    assert (
        "How many planets are there in the solar system?" in vertexai_span.attributes["llm.prompts.0.user"]
    )

def test_vertexai_chat_stream(exporter):
    @workflow("stream_send_message")
    def chat_streaming() -> str:
        """Streaming Chat Example with a Large Language Model"""

        chat_model = ChatModel.from_pretrained("chat-bison")

        parameters = {
            "temperature": 0.8,
            "max_output_tokens": 256,
            "top_p": 0.95,
            "top_k": 40,
        }

        chat = chat_model.start_chat(
            context="My name is Miles. You are an astronomer, knowledgeable about the solar system.",
            examples=[
                InputOutputTextPair(
                    input_text="How many moons does Mars have?",
                    output_text="The planet Mars has two moons, Phobos and Deimos.",
                ),
            ],
        )

        responses = chat.send_message_streaming(
            message="How many planets are there in the solar system?", **parameters
        )

        result = [response for response in responses]
        return result
    chat_streaming()

    spans = exporter.get_finished_spans()
    assert [span.name for span in spans] == [
        "vertexai.send_message",
        "stream_send_message.workflow",
    ]

    vertexai_span = spans[0]
    assert (
        vertexai_span.attributes["llm.top_p"] == 0.95
    )
