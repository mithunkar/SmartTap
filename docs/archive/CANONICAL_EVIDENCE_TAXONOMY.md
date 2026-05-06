# Canonical Evidence-Pattern Taxonomy

SmartTap organizes analytical requests around evidence-pattern families. Each family describes the kind of evidence package the system should return so the user can make the conclusion themselves.

## Core Supported Patterns

- `trend_single`
  Expected queries:
  - "How has ETa changed for mint fields in Klamath County from 2019 to 2024?"
  - "Show precipitation in Hood River County from 2014 to 2022."
  - "How did air temperature evolve near Pendleton from 2016 to 2023?"

- `stat_snapshot`
  Expected queries:
  - "What is the average ETa in Hood River in 2024?"
  - "What was the total precipitation in Ontario in 2023?"
  - "Summarize irrigation efficiency for onion fields in Gilliam County."

- `ranking_categories`
  Expected queries:
  - "What crops were most commonly grown in Yamhill County?"
  - "Which irrigation systems were most common for wheat in Jefferson County?"
  - "Rank the most common crops near Corvallis."

- `distribution_categories`
  Expected queries:
  - "What is the crop distribution in Benton County?"
  - "What share of fields belong to each crop group in Corvallis?"
  - "Show the irrigation-method mix for wheat fields in Jefferson County."

- `comparison_multivariate`
  Expected queries:
  - "Compare AW and ETa in Douglas County from 2018 to 2024."
  - "How did PPT and usable rainfall change for soybean fields in Wasco County?"
  - "Compare PEN_ET and temperature near The Dalles from 2015 to 2024."

- `cross_dataset_comparison`
  Expected queries:
  - "How did rainfall, crop water use, and water demand vary for hazelnut orchards from 2015 to 2023?"
  - "Compare OpenET ETa with AgriMet PEN_ET near Corvallis."
  - "Show crop water use alongside station precipitation for Wallowa County."

## Next-Step Canonical Patterns

- `comparison_grouped`
  Expected queries:
  - "Compare ETa for irrigated vs non-irrigated lentil fields in Grant County."
  - "Which irrigation systems showed the best efficiency for cotton farms in Polk County?"
  - "Show applied water by crop in Malheur County."

- `change_over_period`
  Expected queries:
  - "How much did ETa change between 2018 and 2024 for cabbage farms in Douglas County?"
  - "What changed most before and after 2020 in Morrow County?"
  - "How did irrigation demand differ between 2015 and 2018 versus 2019 and 2023?"

- `ranking_metric`
  Expected queries:
  - "Which crops had the highest ETa in Malheur County from 2015 to 2022?"
  - "Rank counties by applied water in 2024."
  - "Which crop occupied the largest farm area in Linn County?"

- `seasonality_pattern`
  Expected queries:
  - "What seasonal rainfall pattern affected apple orchards in Hood River County?"
  - "Which months usually have the highest ETa for mint in Klamath County?"
  - "Show the typical annual temperature cycle near Medford."

## Deferred Patterns

- `relationship_bivariate`
  Expected queries:
  - "Did rainfall track ETa?"
  - "Does higher temperature align with higher water demand?"

- `composition_over_time`
  Expected queries:
  - "How did crop mix change over time?"
  - "How did irrigation-method shares evolve by year?"

- `outlier_event_detection`
  Expected queries:
  - "Which years were unusually dry?"
  - "When was irrigation demand abnormally high?"

- `availability_coverage`
  Expected queries:
  - "What data is available for this county?"
  - "Which years and variables exist for this crop?"
