/* طيّ البطاقات: زرّ في رأس كل بطاقة يخفي محتواها ويُبقي عنوانها (data-fold = مطويّة افتراضيًّا)؛ الحالة تُحفظ لكل بطاقة، وزرّا «طيّ الكل/فتح الكل» في أعلى الصفحة. */
(function(){
  var KEY="mu_fold",saved={};
  try{saved=JSON.parse(localStorage.getItem(KEY)||"{}")||{}}catch(e){}
  function store(){try{localStorage.setItem(KEY,JSON.stringify(saved))}catch(e){}}
  var cards=[].slice.call(document.querySelectorAll("section.card")).filter(function(c){var h=c.querySelector(":scope > .cardhead");return h&&h.querySelector("h2[id]")});
  function set(card,fold,keep){
    card.classList.toggle("folded",fold);
    var b=card.querySelector(":scope > .cardhead > .foldbtn");
    if(b){b.setAttribute("aria-expanded",String(!fold));b.setAttribute("aria-label",(fold?"فتح ":"طيّ ")+card.querySelector("h2").textContent)}
    if(!keep){saved[card.querySelector("h2").id]=fold?1:0;store()}
    if(!fold)window.dispatchEvent(new Event("resize"));  /* الرسوم التي بُنيت وهي مخفية تُعاد بعرضها الحقيقي */
  }
  cards.forEach(function(card){
    var head=card.querySelector(":scope > .cardhead"),b=document.createElement("button");
    b.type="button";b.className="foldbtn";b.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M6 9l6 6 6-6"/></svg>';
    b.addEventListener("click",function(){set(card,!card.classList.contains("folded"))});
    head.appendChild(b);
    var id=card.querySelector("h2").id;
    set(card,id in saved?saved[id]===1:!card.hasAttribute("data-open"),true);  /* الافتراضي: كل البطاقات مطويّة إلا ما يحمل data-open؛ الشاشة الأولى = الأرقام الثلاثة وأشرطة الحصة */
  });
  /* رابط داخلي إلى عنصر في بطاقة مطويّة يفتحها أولًا (مثل «طلب جديد» في الشريط)، بلا حفظ كي لا يغيّر اختيار الطيّ */
  document.addEventListener("click",function(e){
    var a=e.target.closest&&e.target.closest('a[href^="#"]');if(!a||a.getAttribute("href").length<2)return;
    var t=document.getElementById(a.getAttribute("href").slice(1)),card=t&&t.closest("section.card.folded");
    if(card)set(card,false,true);
  },true);
  var live=document.querySelector(".pagehead .live");
  if(live&&cards.length){
    var all=document.createElement("button");all.type="button";all.className="refresh";all.textContent=cards.some(function(c){return !c.classList.contains("folded")})?"طيّ الكل":"فتح الكل";
    all.addEventListener("click",function(){var fold=cards.some(function(c){return !c.classList.contains("folded")});cards.forEach(function(c){set(c,fold)});all.textContent=fold?"فتح الكل":"طيّ الكل"});
    live.appendChild(all);
  }
})();
