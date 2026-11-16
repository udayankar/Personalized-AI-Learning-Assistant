# Personalized AI Learning Assistant

### Learn from your own material. Ask better questions. Understand concepts more deeply.

The **Personalized AI Learning Assistant** is a project exploring how Artificial Intelligence can make learning more accessible, contextual, and personalized.

The idea is simple: instead of searching through pages of study material or asking questions without context, learners should be able to interact with their own learning resources, receive explanations, and gradually build a better understanding of what they are studying.

The project combines AI-powered question answering with a broader vision of personalized learning.

> 🚧 **Development Status: Actively under development**

---

## 🧠 Why this project?

Learning is not just about finding information. It is about understanding it.

Students often work with lecture notes, textbooks, PDFs, and other study materials. Finding a particular concept in these resources can be time-consuming, and understanding difficult topics often requires additional explanations.

General-purpose AI assistants can explain concepts, but they may not always use the learner's own study material as their source.

This project aims to bring these two experiences closer together.

The current application allows users to upload their study PDFs, ask questions, and receive AI-generated responses that can be supported by references to their uploaded material.

The long-term goal is to go beyond question answering and build an assistant that can understand a learner's progress, identify knowledge gaps, and help determine what to learn next.

---

## ✨ What can you do with it?

### 📚 Learn from your own study materials

Upload PDF documents containing your notes, lecture material, or other educational content.

The assistant processes the documents so you can ask questions about their contents instead of manually searching through every page.

### 🤖 Ask questions naturally

Ask questions in everyday language, just as you would ask a tutor.

For example:

- Explain a concept from my notes.
- What is the difference between two topics?
- Summarize an important idea.
- Help me understand a difficult paragraph.

### 🔎 Check where answers come from

When an answer is supported by your uploaded documents, the application can provide references to the source document, page, and relevant passage.

This makes it easier to verify information instead of blindly trusting an AI-generated response.

### 💡 Answers grounded in your documents

The assistant only returns factual answers that it can verify against retrieved passages from your own uploaded documents. It does not answer from general model knowledge when document evidence is missing.

| Answer type | What it means |
|---|---|
| **Document Supported** | Claims are generated from retrieved passages and include source excerpts and citations when available. |
| **Not found in your documents** | The documents do not contain relevant support, or the system could not verify a document-grounded answer. |

When evidence covers only part of a question, the assistant can return the supported portion and describe what it could not find. Technical processing failures are returned as errors rather than being presented as missing information.

### 🔐 Keep your learning materials private

Uploaded documents and their associated search data are organized separately for individual accounts.

The application also uses authentication and request-protection mechanisms to help protect user sessions and data.

### ⚡ Avoid unnecessary repeated generation

The application includes an exact-answer caching mechanism.

When a previously answered question and its relevant document context still match, the system can reuse the cached response rather than generating the same answer again.

---

## 🔄 How it works

Using the application is straightforward:

1. Create an account and sign in.
2. Upload a PDF containing selectable text.
3. Ask a question about the uploaded material.
4. The application searches for relevant passages.
5. The AI generates an answer using the available context.
6. Review the explanation and its references.

The objective is to make studying from personal learning materials more convenient and interactive.

---

## 🎯 Who is it for?

The application is intended for learners who regularly work with digital study material.

Some examples include:

- **College students** — revisiting lecture notes and understanding difficult concepts.
- **Exam preparation** — asking questions about personal study PDFs.
- **Technical learners** — exploring programming, computer science, mathematics, and other technical subjects.
- **Independent learners** — interacting with educational documents at their own pace.

The current application focuses on PDF-based question answering. It works with PDFs containing extractable text; scanned documents and other file formats are not currently supported.

---

## 🏗️ The bigger vision

The current application focuses on document-based AI assistance, but the broader goal is to create a system that understands more than just the question being asked.

A genuinely personalized learning assistant should gradually understand:

- What a learner already knows.
- Which topics they are trying to learn.
- Where they struggle.
- How they perform in assessments.
- Which concepts they should study next.

The long-term vision is to connect several technologies to support this process.

| Technology | Its intended role |
|---|---|
| Machine Learning | Personalizing and ranking learning recommendations. |
| RAG | Retrieving relevant information from learning resources. |
| Large Language Models | Generating contextual explanations. |
| Assessments | Evaluating a learner's understanding. |
| Learner Modeling | Maintaining an evolving picture of learning progress. |

These components represent the direction of the project, not a claim that every capability is already implemented.

### A possible future learning cycle

```text
       Learn
         |
         v
      Practice
         |
         v
     Assessment
         |
         v
   Evaluate Progress
         |
         v
  Identify Knowledge Gaps
         |
         v
 Recommend What to Learn
         |
         v
       Learn Again
```

The objective is to move beyond isolated AI conversations toward a continuous learning experience.

---

## 🛠️ Built with

The project uses a combination of frontend, backend, database, and AI technologies.

| Technology | Purpose |
|---|---|
| React | Building the user interface. |
| JavaScript | Frontend application logic. |
| FastAPI | Backend API and application logic. |
| Python | Backend and AI processing. |
| PostgreSQL | Persistent application data. |
| Gemini | AI-powered assessment and response generation. |
| Sentence Transformers | Converting text into numerical embeddings. |
| FAISS | Finding relevant passages from uploaded documents. |
| Scikit-learn | Machine Learning experimentation and development. |

For the complete architecture, installation instructions, environment configuration, and implementation details, see the [technical documentation](README-technical.md).

---

## 🚧 Current status and limitations

The project is being developed incrementally.

The current implementation focuses on:

- User authentication.
- PDF document upload and processing.
- Text extraction, chunking, and embedding generation.
- Document retrieval using FAISS.
- AI-powered question answering.
- Document-grounded answers and clear no-information responses.
- Source references and evidence validation.
- Account-specific document storage and retrieval.
- Exact-answer caching.

Some important limitations remain:

- Scanned PDFs without extractable text are not supported.
- Persistent chat history is not available.
- A complete document management experience is not yet available.
- AI-generated answers can still be incomplete or incorrect.
- Learning recommendations and mastery tracking are not implemented yet.
- The project is under development and is not presented as a publicly hosted service.

AI-generated responses should always be reviewed, especially when accuracy is important.

---

## 🔮 Future direction

Future development aims to expand the application beyond document-based question answering.

Potential improvements include:

- Learner profiles and learning goals.
- Learning progress tracking.
- Topic-wise assessments.
- Knowledge-gap identification.
- Personalized learning recommendations.
- Adaptive explanations based on proficiency.
- Support for additional learning resources.
- Evaluation of recommendation quality and learning outcomes.

The intention is to develop these features progressively, with measurable results rather than simply adding AI functionality for its own sake.

---

## 🚀 Getting started

Want to explore or run the project locally?

Visit the [technical documentation](README-technical.md) for:

- Prerequisites.
- Installation instructions.
- Environment configuration.
- Database setup and migrations.
- Backend and frontend startup instructions.
- Testing and evaluation details.

---

## 🤝 Contributing

Suggestions, feedback, and discussions are welcome.

If you find an issue or have an idea that could improve the project, feel free to open an issue or contribute through a pull request.

Please refer to the technical documentation for development and setup details.

---

## 📄 License

The repository currently does not include an explicit open-source license. Reuse, modification, and redistribution permissions have therefore not been formally specified.

---

## 👨‍💻 About the project

**Personalized AI Learning Assistant**

An independently developed project exploring the intersection of Artificial Intelligence, Machine Learning, Generative AI, information retrieval, and personalized education.

The goal is to build something more meaningful than another question-answering chatbot: an assistant that can eventually help learners understand not only what they are studying, but also how they can improve.
