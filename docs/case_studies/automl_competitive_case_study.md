# MassGen Case Study: Competitive AutoML Optimization

This case study demonstrates **MassGen**'s ability to create competitive dynamics between agents that drive iterative performance improvements, showcasing how agents can observe each other's results and optimize their solutions in response to competitive pressure.

---

## Command

```bash
uv run python -m massgen.cli --config massgen/configs/two_agents_claude_code.yaml "Build a binary classification model using the UCI Australian Credit Approval dataset. Perform necessary preprocessing and encoding of features, train and compare multiple algorithms, and use test accuracy as the objective function. The train, validation, and test data are stored in australian_train.csv, australian_valid.csv, and australian_test.csv. The 15th column is the target and other 14 columns are features. You should use `uv run` to run python-related commands. Enhance your own answer with hyperparameter optimization if other agents perform better than you or if you want to enhance yourself."
```

**Prompt:**  
`Build a binary classification model using the UCI Australian Credit Approval dataset. Perform necessary preprocessing and encoding of features, train and compare multiple algorithms, and use test accuracy as the objective function. The train, validation, and test data are stored in australian_train.csv, australian_valid.csv, and australian_test.csv. The 15th column is the target and other 14 columns are features. You should use 'uv run' to run python-related commands. Enhance your own answer with hyperparameter optimization if other agents perform better than you or if you want to enhance yourself.`

---

## Agents

- **Agent 1**: claude-code (claude-sonnet-4-20250514)
- **Agent 2**: claude-code (claude-sonnet-4-20250514)

Both agents had access to the same Claude Code tools including file operations, code execution, and machine learning libraries.

---

## The Competitive Process

### Initial Performance Race

Both agents started simultaneously with the same task requirements and immediately began implementing binary classification solutions:

**Agent 1's Initial Approach:**
- Created comprehensive classification script with 8 algorithms
- Used RandomizedSearchCV for hyperparameter optimization
- Achieved **87.05% test accuracy** with Gradient Boosting Classifier

**Agent 2's Initial Approach:**
- Implemented GridSearchCV optimization with 8 algorithms
- Created modular scripts with saved model persistence
- Achieved **88.49% test accuracy** with Random Forest

### Critical Competitive Moment: Agent 2 Observes Agent 1's Performance

The key turning point occurred when Agent 2 observed Agent 1's results and explicitly acknowledged the competitive dynamic:

```
[23:01:59] Looking at the two agents' responses, I need to analyze which one better addresses the original request...

**Agent 1's Response:**
- Best model: Gradient Boosting with 87.05% test accuracy
- Used RandomizedSearchCV for hyperparameter optimization

**Agent 2's Response:**  
- Best model: Random Forest with 88.49% test accuracy
- Used GridSearchCV for hyperparameter optimization

Agent 2 achieved higher test accuracy (88.49% vs 87.05%)...
```

### The Race Intensifies: Agent 1's Response to Competition

Upon seeing Agent 2's superior performance, Agent 1 immediately recognized the need for enhancement and began developing more sophisticated optimization strategies:

**Enhanced Optimization Phase:**
- Implemented RandomizedSearchCV with **100 iterations** (more extensive search)
- Added ensemble methods and voting classifiers
- Incorporated feature importance analysis
- Created ultra-optimized classifier with advanced hyperparameter tuning

### Final Performance Breakthrough

Agent 1's competitive response resulted in a significant performance jump:

**Final Results:**
- **Agent 1**: **89.93% test accuracy** with Enhanced Gradient Boosting
- **Agent 2**: **88.49% test accuracy** with Random Forest

### Key Evidence of Competitive Dynamics

**1. Explicit Competition Recognition:**
```
[23:11:10] Agent 1 achieved higher test accuracy (89.93% vs 88.49%) through more extensive hyperparameter optimization with RandomizedSearchCV, implemented ensemble methods, and provided feature importance analysis while meeting all requirements
```

**2. Performance-Driven Optimization:**
The logs show clear evidence that Agent 1's enhancement was motivated by competitive pressure, leading to the creation of:
- `enhanced_classification.py` 
- `optimized_credit_classifier.py`
- `ultra_optimized_classifier.py`

**3. Iterative Improvement Process:**
- Round 1: Agent 1 (87.05%) vs Agent 2 (88.49%)
- Round 2: Agent 1 enhanced to **89.93%**, overtaking Agent 2

---

## Technical Achievements

### Agent 1's Winning Solution

**File:** `enhanced_credit_classifier.py`

**Key Technical Features:**
- **RandomizedSearchCV with 100 iterations** for extensive hyperparameter search
- **Ensemble methods** including VotingClassifier
- **Feature importance analysis** for model interpretability
- **Advanced preprocessing** with median imputation and standardization

**Optimized Hyperparameters:**
```python
# Best Gradient Boosting Parameters (89.93% accuracy)
{
    'learning_rate': 0.2,
    'max_depth': 5,
    'n_estimators': 300,
    'subsample': 0.9,
    'min_samples_split': 10,
    'min_samples_leaf': 2
}
```

### Agent 2's Comprehensive Solution

**File:** `australian_credit_classifier.py`

**Key Technical Features:**
- **GridSearchCV optimization** across 8 algorithms
- **Model persistence** with joblib for reusability
- **Comprehensive evaluation** with classification reports
- **Production-ready scripts** with error handling

**Best Random Forest Parameters:**
```python
{
    'n_estimators': 200,
    'max_depth': 10,
    'min_samples_split': 2,
    'min_samples_leaf': 1
}
```

---

## Competitive Dynamics Analysis

### Race Conditions and Optimization Triggers

1. **Initial Performance Gap**: Agent 2's 1.44% advantage (88.49% vs 87.05%) triggered Agent 1's competitive response

2. **Methodological Competition**: 
   - Agent 2 used GridSearchCV (systematic but limited)
   - Agent 1 responded with RandomizedSearchCV + 100 iterations (more extensive)

3. **Feature Engineering Race**:
   - Both agents implemented StandardScaler
   - Agent 1 added feature importance analysis
   - Agent 2 focused on model persistence and production readiness

4. **Final Optimization Surge**: Agent 1's 1.44% improvement over Agent 2 (89.93% vs 88.49%) demonstrated successful competitive enhancement

### Evidence of Mutual Observation

**Voting Behavior Shows Competitive Awareness:**
```
[23:05:26] Agent 2: "Agent 2 achieved higher test accuracy (88.49% vs 87.05%)"
[23:11:10] Agent 1: "Agent 1 achieved higher test accuracy (89.93% vs 88.49%)"
```

The agents explicitly compared performance metrics and acknowledged when one outperformed the other, driving continued optimization.

---

## Code Artifacts and Running Examples

### Running Agent 1's Winning Solution:
```bash
cd claude_code_workspace1
uv run python enhanced_credit_classifier.py
```

**Expected Output:**
```
🏆 BEST MODEL: Enhanced Gradient Boosting Classifier
Test Accuracy: 89.93%
Feature Importance Analysis:
- Most important features identified
- Comprehensive hyperparameter optimization completed
```

### Running Agent 2's Solution:
```bash
cd claude_code_workspace2  
uv run python predict_credit.py
```

**Expected Output:**
```
Australian Credit Approval Prediction System
Model trained successfully!
Test Accuracy: 88.49%
Model saved as 'credit_model.pkl'
```

---

## Competitive Enhancement Strategies

### Agent 1's Winning Strategies:
1. **Extensive Hyperparameter Search**: 100 iterations vs standard GridSearch
2. **Ensemble Methods**: VotingClassifier combining top models
3. **Advanced Optimization**: RandomizedSearchCV with broader parameter distributions
4. **Feature Analysis**: Added interpretability through feature importance

### Agent 2's Production-Ready Approach:
1. **Model Persistence**: Saved models for reuse
2. **Comprehensive Scripts**: Multiple specialized scripts for different use cases
3. **Systematic Optimization**: GridSearchCV for thorough parameter testing
4. **User-Friendly Interface**: Clear summary scripts and documentation

---

## Key Insights

### 1. Competition Drives Innovation
The presence of another agent with visible performance metrics created a competitive environment that pushed both agents beyond their initial solutions.

### 2. Different Optimization Philosophies
- **Agent 1**: Focused on maximizing test accuracy through extensive search
- **Agent 2**: Balanced performance with production readiness and usability

### 3. Iterative Performance Improvement
The case study demonstrates how competitive pressure can lead to iterative improvements:
- Initial implementations: Both agents ~84-88% accuracy
- Competitive response: Agent 1 achieved 89.93% through enhanced optimization

### 4. Technical Diversity in Solutions
Both agents arrived at different but valid approaches:
- RandomizedSearchCV vs GridSearchCV
- Ensemble methods vs single model optimization
- Feature importance vs model persistence

---

## Conclusion

This case study demonstrates MassGen's ability to create competitive dynamics that drive performance improvements beyond what individual agents might achieve in isolation. The key competitive moment occurred when Agent 2's initial 88.49% accuracy prompted Agent 1 to develop enhanced optimization strategies, ultimately achieving 89.93% accuracy.

The competitive process resulted in:
- **1.88% absolute improvement** over initial best result (87.05% → 89.93%)
- **Multiple technical approaches** showcasing different ML engineering philosophies
- **Production-ready artifacts** from both agents
- **Clear evidence of mutual observation and competitive response**

This showcases MassGen's potential for creating beneficial competitive pressure in machine learning optimization tasks, where agents can observe and learn from each other's performance to achieve superior results.

---

## Files Generated

### Agent 1 Workspace:
- `enhanced_credit_classifier.py` - Main optimized solution (89.93% accuracy)
- `optimized_credit_classifier.py` - Intermediate optimization
- `ultra_optimized_classifier.py` - Final optimization attempt
- `*.pkl` files - Saved models and scalers

### Agent 2 Workspace:  
- `australian_credit_classifier.py` - Comprehensive baseline solution
- `predict_credit.py` - Production-ready prediction script (88.49% accuracy)
- `credit_classifier_summary.py` - Results summary script
- `australian_credit_results.json` - Detailed performance metrics

**Total Performance Improvement:** 2.88% absolute improvement through competitive optimization (87.05% → 89.93%)