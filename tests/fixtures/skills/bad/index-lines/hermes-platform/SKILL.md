---
name: hermes-platform
description: "Indexes verified Hermes primitives with doc paths. Use when designing or changing any profile, skill, cron or board."
---

# Hermes platform

## When to Use

- A kanban card asks for a new dashboard widget.
- A widget renders wrong data or breaks the layout.

## Procedure

1. Read the data contract in `references/widget-contract.md`.
2. Copy `templates/widget.html` into the site repo.
3. Run `scripts/render_widget.py --input data.json` to preview it.
4. Run `scripts/check_widget.sh widget.html` before handing off.
5. Check field group 1 against the contract.
6. Check field group 2 against the contract.
7. Check field group 3 against the contract.
8. Check field group 4 against the contract.
9. Check field group 5 against the contract.
10. Check field group 6 against the contract.
11. Check field group 7 against the contract.
12. Check field group 8 against the contract.
13. Check field group 9 against the contract.
14. Check field group 10 against the contract.
15. Check field group 11 against the contract.
16. Check field group 12 against the contract.
17. Check field group 13 against the contract.
18. Check field group 14 against the contract.
19. Check field group 15 against the contract.
20. Check field group 16 against the contract.
21. Check field group 17 against the contract.
22. Check field group 18 against the contract.
23. Check field group 19 against the contract.
24. Check field group 20 against the contract.
25. Check field group 21 against the contract.
26. Check field group 22 against the contract.
27. Check field group 23 against the contract.
28. Check field group 24 against the contract.
29. Check field group 25 against the contract.
30. Check field group 26 against the contract.
31. Check field group 27 against the contract.
32. Check field group 28 against the contract.
33. Check field group 29 against the contract.
34. Check field group 30 against the contract.
35. Check field group 31 against the contract.
36. Check field group 32 against the contract.
37. Check field group 33 against the contract.
38. Check field group 34 against the contract.
39. Check field group 35 against the contract.
40. Check field group 36 against the contract.
41. Check field group 37 against the contract.
42. Check field group 38 against the contract.
43. Check field group 39 against the contract.
44. Check field group 40 against the contract.
45. Check field group 41 against the contract.
46. Check field group 42 against the contract.
47. Check field group 43 against the contract.
48. Check field group 44 against the contract.
49. Check field group 45 against the contract.
50. Check field group 46 against the contract.
51. Check field group 47 against the contract.
52. Check field group 48 against the contract.
53. Check field group 49 against the contract.
54. Check field group 50 against the contract.
55. Check field group 51 against the contract.
56. Check field group 52 against the contract.
57. Check field group 53 against the contract.
58. Check field group 54 against the contract.
59. Check field group 55 against the contract.
60. Check field group 56 against the contract.
61. Check field group 57 against the contract.
62. Check field group 58 against the contract.
63. Check field group 59 against the contract.
64. Check field group 60 against the contract.
65. Check field group 61 against the contract.
66. Check field group 62 against the contract.
67. Check field group 63 against the contract.
68. Check field group 64 against the contract.
69. Check field group 65 against the contract.
70. Check field group 66 against the contract.
71. Check field group 67 against the contract.
72. Check field group 68 against the contract.
73. Check field group 69 against the contract.
74. Check field group 70 against the contract.
75. Check field group 71 against the contract.
76. Check field group 72 against the contract.
77. Check field group 73 against the contract.
78. Check field group 74 against the contract.
79. Check field group 75 against the contract.
80. Check field group 76 against the contract.
81. Check field group 77 against the contract.
82. Check field group 78 against the contract.
83. Check field group 79 against the contract.
84. Check field group 80 against the contract.

## Pitfalls

- Never invent fields the contract does not define.
- Keep every color in the design tokens file.

## Verification

- `scripts/check_widget.sh` exits 0.
- The preview matches the card's acceptance criteria.
