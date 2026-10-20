// Manuscript author-date CSL: initials, complete bibliography author lists,
// and year-suffix disambiguation (avoids built-in style truncation in Typst 0.14.2).
#let manuscript-style = bytes(```xml
<style xmlns="http://purl.org/net/xbiblio/csl" version="1.0" class="in-text" default-locale="en-US" demote-non-dropping-particle="never">
  <info>
    <title>DNLI author-date</title>
    <id>urn:dnli:author-date</id>
    <updated>2026-10-15T00:00:00+00:00</updated>
  </info>
  <macro name="authors">
    <names variable="author">
      <name name-as-sort-order="all" sort-separator=", " initialize-with=". " and="symbol" delimiter=", " delimiter-precedes-last="always"/>
    </names>
  </macro>
  <macro name="year">
    <date variable="issued"><date-part name="year"/></date>
    <text variable="year-suffix"/>
  </macro>
  <citation et-al-min="3" et-al-use-first="1" disambiguate-add-year-suffix="true">
    <layout prefix="(" suffix=")" delimiter="; ">
      <group delimiter=", ">
        <names variable="author"><name form="short" and="symbol" delimiter=", "/><et-al/></names>
        <text macro="year"/>
      </group>
    </layout>
  </citation>
  <bibliography hanging-indent="true" entry-spacing="1">
    <sort><key macro="authors"/><key macro="year"/><key variable="title"/></sort>
    <layout>
      <group delimiter=" ">
        <text macro="authors" suffix="."/>
        <text macro="year" prefix="(" suffix=")."/>
        <text variable="title" suffix="."/>
        <choose>
          <if type="article-journal">
            <group delimiter=", " suffix=".">
              <text variable="container-title" font-style="italic"/>
              <group>
                <text variable="volume" font-style="italic"/>
                <text variable="issue" prefix="(" suffix=")"/>
              </group>
              <text variable="page"/>
            </group>
          </if>
          <else>
            <group delimiter=", " suffix=".">
              <text variable="container-title" font-style="italic"/>
              <text variable="volume"/>
              <text variable="page"/>
            </group>
          </else>
        </choose>
        <choose>
          <if variable="DOI"><text variable="DOI" prefix="https://doi.org/"/></if>
          <else><text variable="URL"/></else>
        </choose>
      </group>
    </layout>
  </bibliography>
</style>
```.text)
#set document(title: "Hearsay or Fact? How Framing and Elicitation Shape LLM Probability Updates", author: "An-Sheng Jhang")
#set page(paper: "a4", margin: (x: 22mm, y: 20mm), numbering: "1")
#set text(font: "New Computer Modern", size: 11pt, lang: "en")
#set par(justify: true, leading: .6em)
#set heading(numbering: "1.1")
#set cite(style: manuscript-style)
#set figure(gap: .65em)
#show figure.caption: set text(size: 9pt)
#show figure.where(kind: table): set figure.caption(position: top)
#align(center)[
  #set par(justify: false)
  #text(size: 18pt, weight: "bold", hyphenate: false)[Hearsay or Fact? How Framing and Elicitation Shape LLM Probability Updates]

  #v(8pt)
  An-Sheng Jhang \
  Dongguan University of Technology \
  #link("mailto:ansheng.jhang@gmail.com")[ansheng.jhang\@gmail.com]
]
#v(8pt)
#block(inset: (x: 8pt))[
  #align(center, strong[Abstract])
  #include "abstract.typ"
]
#v(8pt)
#include "body.typ"
#block[
  // Typst 0.14.2 retains the CSL period after question-ending titles.
  #show regex("\\?\\."): [?]
  #bibliography("../references.bib", title: "References", style: manuscript-style)
]
