# Personalized AI Learning Assistant

### A learning platform that adapts to what you know and what you need to learn next.

The Personalized AI Learning Assistant is an AI-powered learning platform designed to combine personalized learning recommendations, knowledge-grounded AI assistance, and adaptive explanations in one system.

The platform uses **Machine Learning** to personalize learning resources, **Retrieval-Augmented Generation (RAG)** to provide grounded answers from educational content, and **Large Language Models (LLMs)** to generate contextual explanations based on the learner's current knowledge and goals.

> 🚧 **Status: Actively under development**

---

## 🧠 Why Personalized Learning?

Traditional learning platforms often provide the same content and learning paths to every user.

General-purpose AI assistants can explain almost anything, but they usually focus on the current question rather than maintaining a structured understanding of the learner.

A beginner and an advanced learner asking:

> "Explain Python multithreading."

should not necessarily receive the same explanation.

The assistant aims to understand:

- What the learner already knows
- Their current proficiency
- What they want to learn
- What they have already studied
- How they performed in previous assessments
- What they should learn next

This allows the platform to move beyond simple AI question-answering toward a more **personalized learning experience**.

---

## ✨ Features

### 👤 Learner Profile

The platform maintains a learner profile containing information such as:

- Skills
- Proficiency levels
- Learning goals
- Completed topics
- Learning history
- Assessment performance
- Interaction history

This information forms the foundation of the learner's personalized experience.

---

### 🎯 Personalized Recommendations

The system recommends learning resources according to the learner's current state.

Recommendations can consider:

- Current skills
- Skill proficiency
- Learning goals
- Topic prerequisites
- Previous learning activity
- Assessment results
- Resource difficulty
- Topic similarity

The recommendation system ranks resources according to their relevance to the individual learner.

---

### 🤖 Machine Learning

Machine Learning is used primarily for **personalization and recommendation**.

Instead of simply asking an LLM:

> "What should this user learn?"

the system uses structured learner and resource information to produce ranked recommendations.

```text
Learner Profile
      +
Resource Information
      +
Interaction History
      ↓
Machine Learning
      ↓
Relevance Scores
      ↓
Ranked Recommendations
```

For users with little or no interaction history, the system can fall back to content-based and prerequisite-based recommendations.

---

### 📚 AI-Powered Learning Assistant

Users can ask questions about topics they are learning.

For example:

- Explain gradient descent.
- Why does Python have a GIL?
- How does an HTTP request work?
- What should I learn after SQL joins?

The assistant uses the learner's context to provide an appropriate response rather than treating every conversation independently.

---

### 🔎 Retrieval-Augmented Generation

The assistant uses RAG to retrieve relevant information from a curated educational knowledge base before generating an answer.

```text
Educational Documents
        ↓
Text Processing
        ↓
Chunking
        ↓
Embeddings
        ↓
Vector Database
        ↓
Semantic Retrieval
        ↓
Relevant Context
        ↓
LLM
        ↓
Grounded Response
```

This allows the assistant to use project-specific educational content as a source of information instead of relying entirely on the LLM's pretrained knowledge.

Where possible, retrieved sources can also be shown to the learner.

---

### 🧩 Adaptive Explanations

The assistant can adjust the depth and technicality of explanations according to the learner's proficiency.

For example, a beginner learning Python multithreading may receive:

- Simple concepts
- Analogies
- Basic examples
- Practical use cases

An advanced Python learner may instead receive explanations involving:

- CPython internals
- GIL
- Native threads
- Operating-system scheduling
- Kernel-level execution
- CPU behavior

The LLM generates the explanation, while the learner model provides the context required for personalization.

---

### 📝 Assessments

The platform can evaluate whether a learner actually understood a topic.

```text
Learn
  ↓
Practice
  ↓
Assessment
  ↓
Performance
  ↓
Mastery Update
```

Assessment results can be used to update the learner's estimated mastery and influence future recommendations.

This prevents the system from assuming that simply reading an explanation means the learner has mastered the topic.

---

### 🔄 Continuous Personalization

The learner model evolves as the user interacts with the platform.

```text
Learn
  ↓
Interact
  ↓
Assess
  ↓
Update Mastery
  ↓
Recommend
  ↓
Learn Again
  ↺
```

The objective is to create a continuously improving learning experience rather than a collection of independent AI conversations.

---

### 🛡️ Intelligent Fallbacks

The system accounts for situations where individual components may not have enough information.

For example:

**New learner**

```text
No interaction history
        ↓
Content + Skill + Goal based recommendation
```

**Insufficient RAG coverage**

```text
Query
  ↓
Relevant content available?
   /        \
 Yes         No
 ↓            ↓
RAG       Broader retrieval
              ↓
        Still insufficient?
          /          \
        Yes           No
         ↓             ↓
 Knowledge gap        RAG
```

This helps prevent unsupported information or weak recommendations from being treated as reliable results.

---

## 🏗️ Architecture

The platform is designed as a full-stack AI application with a React frontend, FastAPI backend, Machine Learning services, and a RAG pipeline.

```text
                         USER
                           │
                           ▼
                  ┌─────────────────┐
                  │ React Frontend  │
                  └────────┬────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │ FastAPI Backend │
                  └────────┬────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │  Learner Model  │
                  └────────┬────────┘
                           │
              ┌────────────┴────────────┐
              │                         │
              ▼                         ▼
     ┌─────────────────┐       ┌─────────────────┐
     │ ML Recommendation│       │   RAG Pipeline  │
     └────────┬────────┘       └────────┬────────┘
              │                         │
              ▼                         ▼
     ┌─────────────────┐       ┌─────────────────┐
     │ Recommendation  │       │ Vector Database │
     │   Validation    │       └────────┬────────┘
     └────────┬────────┘                │
              │                         ▼
              │                ┌─────────────────┐
              │                │ Retrieved Context│
              │                └────────┬────────┘
              │                         │
              └────────────┬────────────┘
                           ▼
                    ┌─────────────┐
                    │ LLM / GenAI │
                    └──────┬──────┘
                           │
                           ▼
                 Personalized Response
                           │
                           ▼
                    ┌─────────────┐
                    │  Assessment │
                    └──────┬──────┘
                           │
                           ▼
                     Mastery Update
                           │
                           ▼
                    Learner Model
                           │
                           └──────────────↺
```

The frontend handles the user experience and interaction with the platform.

The FastAPI backend coordinates authentication, learner data, recommendations, AI services, learning history, and application logic.

The ML layer handles learner-aware recommendations, while the RAG layer handles retrieval of relevant educational knowledge.

The LLM combines the retrieved context with learner information to generate the final response.

---

## 🛠️ Tech Stack

### Frontend
- React
- JavaScript
- React Router
- CSS

### Backend
- Python
- FastAPI

### Machine Learning
- Python
- NumPy
- Pandas
- Scikit-learn

### AI / NLP
- Large Language Models
- Embedding Models
- Natural Language Processing
- Retrieval-Augmented Generation
- Vector Search
- Vector Database
- Semantic Similarity Search

### Database
- PostgreSQL

### Development
- Git
- GitHub
- VS Code

---

## 📁 Project Structure

The project is currently under active development, and the internal folder structure is evolving alongside the architecture.
A detailed project structure will be documented here once the core application architecture is finalized.

---

## 🚧 Development Status

The project is being developed incrementally, with individual AI and application components being built and integrated progressively.

### Completed
- RAG pipeline architecture
- Document ingestion pipeline
- Document preprocessing
- Text chunking
- Embedding generation
- Vector storage
- Semantic retrieval
- Initial RAG question-answering pipeline

### In Development
- Learner profile system
- Learner model
- Machine Learning recommendation system
- Learning-resource representation
- Recommendation ranking
- FastAPI backend
- React frontend
- LLM integration
- Assessment system
- Feedback system

### Planned
- Mastery estimation
- Recommendation validation
- Continuous learner-model updates
- Adaptive assessments
- Recommendation evaluation
- RAG evaluation
- End-to-end personalization
- Production deployment

---

## 🔌 Backend API

The backend is being built with FastAPI and will provide REST endpoints for the platform's core functionality.

Planned API areas include:

- Authentication
- Users
- Learner Profiles
- Skills
- Learning Goals
- Learning Resources
- Recommendations
- Learning Sessions
- AI Assistant
- Assessments
- Feedback
- Learning History

API documentation will expand as additional backend functionality is implemented.

---

## 🧪 Evaluation

The platform will evaluate its major components independently as well as the complete learning experience.

### Recommendation
- Precision@K
- Recall@K
- NDCG
- Recommendation relevance

### RAG
- Retrieval relevance
- Retrieval precision
- Retrieval recall
- Answer correctness
- Groundedness
- Source accuracy

### Learning
- Assessment performance
- Mastery improvement
- Learning gain
- Recommendation effectiveness

The goal is to measure whether personalization actually improves the learning experience rather than simply demonstrating that individual AI components work.

---

## 🎯 Vision

The long-term goal is to create a learning assistant that can understand more than just the question currently being asked.

Instead of only answering:

> "What is this?"

the platform aims to help answer:

- "What should I learn next?"
- "What do I already know?"
- "How deeply should this be explained to me?"
- "Did I actually understand it?"
- "What should I work on after this?"

The combination of Machine Learning, RAG, and Generative AI allows each technology to handle a different part of the learning process.

```text
Machine Learning
"What should I learn?"

        ↓

RAG
"What relevant knowledge should be used?"

        ↓

LLM
"How should it be explained?"

        ↓

Assessment
"Did the learner understand?"

        ↓

Learner Model
"What do we know about the learner now?"

        ↓

Machine Learning
"What should the learner learn next?"
```

---

## 🚀 Future Direction

The next stages of development focus on connecting the existing RAG system with the learner model, recommendation engine, backend, and frontend.

Future development will focus on:

- Better learner modeling
- More accurate recommendations
- Improved retrieval
- Adaptive explanations
- Assessment-driven personalization
- Stronger feedback loops
- Better evaluation
- Production deployment

As development progresses, this README will be updated alongside the application.

---

## 👨‍💻 Author

**Udayan Kar**

An independently developed project focused on exploring Artificial Intelligence, Machine Learning, Generative AI, RAG systems, recommendation systems, and full-stack application development.
