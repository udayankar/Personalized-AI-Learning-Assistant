import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

client = genai.Client(api_key=os.getenv("LLM_API_KEY"))

def Generate_answer(question, context) :
    prompt = f"""You are a helpful AI learning assistant. Answer the student's question using the provided study material. Study material : {context}Student question : {question} Give a clear and educational answer."""
    response = client.models.generate_content(model="gemini-3.6-flash" ,contents=prompt)

    return response.text

if __name__ == "__main__":

    question = "What is image thresholding?"

    context = """
    Simple thresholding is a technique where the same threshold
    is applied to every pixel. If the pixel value is smaller than
    the threshold, it is set to 0. Otherwise, it is set to the
    maximum value.
    """

    answer = Generate_answer(question, context)

    print("\nQuestion:")
    print(question)

    print("\nAnswer:")
    print(answer)