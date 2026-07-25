from app.decision.decision_engine import DecisionEngine

engine = DecisionEngine()

result = engine.evaluate(
    qr_result={
        "domain_authenticity": True,
        "is_secure": True,
    },
    comparison={
        "score": 100
    },
    ai_score=0.69,
    tamper_score=0.30,
    cnn_probability=0.09,
    rf_result={
        "confidence": 0.31
    }
)

print(result)