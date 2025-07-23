# Congressional Bills Analysis

Hi there! 👋

This is a personal project where I'm exploring text and vote data on bills introduced in the United States Congress. I found this dataset through Brown University's LUNAR Lab and thought it would be a great way to learn more about language, politics, and a little bit of NLP along the way.

### Why This Repo Exists

I'm a student (not at Brown) with a growing interest in AI / ML, but I'm still pretty new to Python and all the tools that come with it. This repo is mostly a place for me to experiment, try things out, and see what I can discover. Maybe down the line, I'll have some cool findings to share :)

### Project Structure

The dataset is absolutely gargantuan, so here's an abstracted project structure:

```
congressional-bills/
├── analysis/
│   ├── old/
│   │   ├── summary_stats.py
│   │   └── [data files here]
│   ├── resort.py
│   ├── short_vs_official_logprob.py
│   ├── summary_stats.py
│   ├── tmp
│   └── [data files here]
├── lm/
│   ├── ids.txt
│   ├── official_titles/
│   │   └── [official title data files here]
│   ├── preprocess.py
│   ├── pull_out_logprob.py
│   ├── score_sents.py
│   ├── short_titles/
│   │   └── [short title data files here]
│   ├── train_and_score_srilm.sh
│   ├── train_and_score.sh
│   └── [data files here]
└── processing/
    ├── clean_up.py
    ├── get_titles_and_summaries.py
    ├── get_titles.py
    ├── pos.sh
    ├── preprocess.py
    ├── parsing/
    │   ├── aligned_titles.py
    │   ├── clean.py
    │   ├── clean.pyc
    │   ├── filter_ppdb_pairs_to_vocab.py
    │   ├── get_vocab.py
    │   ├── log_odds.py
    │   ├── logs/
    │   ├── metadata/
    │   ├── paired_log_odds.py
    │   ├── run-parser-local.sh
    │   ├── run-parser.sh
    │   ├── score_pairs.py
    │   ├── setup_dirs.py
    │   ├── titles-parsed/
    │   ├── titles-raw/
    │   ├── uniq.py
    │   └── [parsing/ data files here]
    └── [processing/ data files here]
```

- **analysis/**: Scripts and data for analyzing bill text and statistics.
- **lm/**: Language modeling scripts and data, including tools for working with official and short titles.
- **processing/**: Scripts for cleaning, extracting, and preparing data. The `parsing/` subfolder contains more specialized scripts and data for parsing bill titles and related information.

### What I'm Curious About

LUNAR Lab's page poses a few interesting questions, specifically, I'm look at:

1. **Can I find pairs of phrases that mean the same thing but are used in very different ways?**
   - For example, phrases like "chain migration" vs. "family reunification" or "estate tax" vs. "death tax". They refer to the exact same thing but hold certain connotations. What other examples can be found?

2. **Are there patterns in how "short titles" are used for congressional bills?**
   - Is there a way to predict or generate a short title from a longer, official bill title? What trends or quirks show up in the data? I'd ultimately like to be able to generate short titles from the official ones.

### Important Links

LUNAR Lab Starter Projects: https://cs.brown.edu/people/epavlick/join-us.html

Dataset: https://cs.brown.edu/people/epavlick/congressional-bills.tgz

### Getting Started (If You're Like Me)

If you somehow happen upon this repository and are also new to Python or just curious, feel free to poke around. I'm still figuring things out, so this repo might be a bit messy or experimental. Maybe you'll find something interesting, or maybe you'll have ideas for what to try next. I'd love to hear from you!

---

Thanks for stopping by! If I end up with results or insights worth sharing, I'll try to update this README or post about it somewhere. Until then, happy exploring! 🚀
