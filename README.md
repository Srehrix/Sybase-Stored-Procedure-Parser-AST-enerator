
---

# Sybase Stored Procedure Parser (AST Generator)

![Python](https://img.shields.io/badge/python-3.x-blue.svg)
![ANTLR](https://img.shields.io/badge/antlr-4.13-red.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

---

## 📌 Overview

**Tool 2** of the Sybase-to-PostgreSQL modernization suite. This tool **parses Sybase stored procedures** and generates an **Abstract Syntax Tree (AST)** in JSON format. It is designed to power downstream tools like documentation generators, lineage analyzers, and PostgreSQL transformers.

---

## ✅ Features

✔ Parse **Sybase SQL stored procedures** into structured AST
✔ Extract **parameters**, **variables**, **statements**, and **cursors**
✔ Generate **JSON output** for integration with other tools
✔ Built with **ANTLR grammar** or a **custom parser**

---

## 🛠️ Tech Stack

* [Python 3.x](https://www.python.org/)
* [ANTLR](https://www.antlr.org/) (Python runtime)
* JSON serialization

---

## 📂 Input & Output

### **Input**

A `.sql` file containing a **Sybase stored procedure**:

```sql
CREATE PROCEDURE sp_insert_order
    @order_id INT,
    @cust_id INT
AS
BEGIN
    INSERT INTO orders VALUES (@order_id, @cust_id);
END
```

### **Output**

A JSON file representing the **AST**:

```json
{
  "procedure": "sp_insert_order",
  "params": [
    {"name": "@order_id", "type": "INT"},
    {"name": "@cust_id", "type": "INT"}
  ],
  "variables": [],
  "cursors": [],
  "statements": [
    "INSERT INTO orders VALUES (@order_id, @cust_id);"
  ]
}
```

---

## 📦 Installation

Clone the repo:

```bash
git clone https://github.com/Srehrix/Tool-2-Sybase-Stored-Procedure-Parser-AST-Generator-.git
cd Tool-2-Sybase-Stored-Procedure-Parser-AST-Generator-
```

Install dependencies:

```bash
pip install -r requirements.txt
```

If using ANTLR:

```bash
brew install antlr
# or download from https://www.antlr.org/download.html
```

---

## ▶️ Usage

Run the parser:

```bash
python parser.py --input sample.sql --output ast.json
```

Options:

```
--input    Path to the Sybase stored procedure file (.sql)
--output   Path to save the generated AST (.json)
```

---

## 🔗 Integration Flow

This tool fits into the **modernization pipeline**:

```mermaid
flowchart TD
    A[Sybase .sql Files] --> B[Tool 1: Indexer]
    A --> C[Tool 2: Parser (This Tool)]
    B --> D[Tool 3: Documentation Generator]
    C --> D
    B --> E[Tool 4: Lineage Analyzer]
    C --> E
    C --> F[Tool 5: SP Transformer]
    F --> G[Tool 6: Validator & Report]
    E --> G
    D --> G
    G --> H[Postgres .sql Files]


```

---

## 📂 Project Structure

```
tool2_parser/
│
├── parser.py           # Main parser script
├── grammar/            # ANTLR grammar files
├── samples/            # Sample .sql and AST files
├── requirements.txt    # Python dependencies
└── README.md           # Project documentation
```

---

## 🛡️ License

This project is licensed under the **MIT License**. See [LICENSE](LICENSE) for details.

---

## 🤝 Contributing

1. Fork the repo
2. Create a new branch (`feature/my-feature`)
3. Commit your changes (`git commit -m 'Add my feature'`)
4. Push to the branch (`git push origin feature/my-feature`)
5. Open a Pull Request

---
