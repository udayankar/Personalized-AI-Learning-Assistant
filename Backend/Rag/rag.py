from vector_store import (Load_vector_store,Retrieve)
from embedder import model
from generator import Generate_answer

def Ask_question(question):
    index, chunks = Load_vector_store()
    results = Retrieve(question,index,chunks,model,k=5)
    context = ""
    for result in results:
        context += f"""Source: {result.get("source", "Unknown")}Page: {result["page"]} {result["text"]}"""
    answer = Generate_answer(question,context)

    return answer, results

if __name__ == "__main__":

    question = "What is image thresholding?"

    answer, results = Ask_question(
        question
    )


    print("\nQuestion:")

    print(question)


    print("\nAnswer:")

    print(answer)


    print("\nSources:")

    for result in results:

        print(
            f"- {result.get('source', 'Unknown')} "
            f"(Page {result['page']})"
        )