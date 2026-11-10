(command_name) @function
(line_comment) @comment
(block_comment) @comment
(begin command: _ @keyword)
(end command: _ @keyword)
(section text: (curly_group (_) @title))
(subsection text: (curly_group (_) @title))
(subsubsection text: (curly_group (_) @title))
(inline_formula) @string.special
(displayed_equation) @string.special
["{" "}" "[" "]"] @punctuation.bracket

