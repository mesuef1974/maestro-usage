/* الشاشات: شاشة واحدة ظاهرة بحسب الرابط؛ رابطٌ إلى عنصر داخل شاشة يفتحها ثم ينزل إليه. بلا JS تظهر الشاشات كلها صفحةً واحدة. */
(function(){
  var views=[].slice.call(document.querySelectorAll(".view")),links=[].slice.call(document.querySelectorAll(".nav a[href^='#']")),base=document.title;
  if(!views.length)return;
  function show(hash){
    var id=hash.slice(1),own=document.getElementById("v-"+id),inner=!own&&id?document.getElementById(id):null;
    var view=own||(inner&&inner.closest(".view"))||views[0],name=view.getAttribute("data-view");
    views.forEach(function(v){v.hidden=v!==view});
    links.forEach(function(a){if(a.getAttribute("href")==="#"+name)a.setAttribute("aria-current","page");else a.removeAttribute("aria-current")});
    var head=view.querySelector(".gh");
    document.title=(head?head.textContent+" · ":"")+base;
    window.dispatchEvent(new Event("resize"));  /* الرسوم التي بُنيت وهي مخفية تُعاد بعرضها الحقيقي */
    if(inner&&!inner.closest(".pagehead"))inner.scrollIntoView();
    else requestAnimationFrame(function(){window.scrollTo({top:0,behavior:"instant"})});  /* بعد قفز المتصفّح إلى العنوان */
  }
  window.addEventListener("hashchange",function(){show(location.hash);var h=views.filter(function(v){return!v.hidden})[0],g=h&&h.querySelector(".gh");if(g){g.setAttribute("tabindex","-1");g.focus({preventScroll:true})}});
  show(location.hash);
})();
/* جداول بلا caption: اسمها من ملخّص details الحاضن أو أقرب عنوان قبلها، لقارئ الشاشة */
(function(){
  function nameTables(){[].forEach.call(document.querySelectorAll("table"),function(t){
    if(t.querySelector("caption")||t.getAttribute("aria-label"))return;
    var d=t.closest("details"),s=d&&d.querySelector("summary"),n=t,h=null;
    while(!h&&n&&n.tagName!=="MAIN"&&n.tagName!=="BODY"){var p=n.previousElementSibling;while(p&&!h){h=/^H[1-6]$/.test(p.tagName)?p:p.querySelector&&p.querySelector("h2,h3,h4");p=p.previousElementSibling}n=n.parentElement}
    var st=s&&s.textContent.trim(),ht=h&&h.textContent.trim(),name=st&&!/^عرض الجدول$/.test(st)?st:(ht||st);
    if(!name){var v=t.closest(".view"),g=v&&v.querySelector(".gh"),th=t.querySelector("th");name=((g&&g.textContent.trim())||"جدول")+(th?" — "+th.textContent.trim():"")}
    if(name)t.setAttribute("aria-label",name.replace(/\s+/g," ").slice(0,80));
  });}
  /* منطقة تمرير بلا محتوى قابل للتركيز: تُنال بلوحة المفاتيح (axe: scrollable-region-focusable) */
  function scrollables(){[].forEach.call(document.querySelectorAll(".wrap,.rl-log"),function(w){
    var over=(w.scrollWidth>w.clientWidth+1||w.scrollHeight>w.clientHeight+1)&&w.offsetParent!==null;
    if(over&&!w.hasAttribute("tabindex")&&!w.querySelector("a[href],button,input,select,textarea,[tabindex]")){
      var tb=w.querySelector("table"),n=tb&&tb.getAttribute("aria-label");
      w.setAttribute("tabindex","0");if(!w.classList.contains("rl-log"))w.setAttribute("role","group");w.setAttribute("aria-label",n||(w.classList.contains("rl-log")?"سجل التشغيل":"منطقة قابلة للتمرير"));
    }})}
  function all(){nameTables();scrollables()}
  all();setTimeout(all,800);setTimeout(all,3000);window.addEventListener("hashchange",function(){setTimeout(all,150)});window.addEventListener("resize",function(){setTimeout(scrollables,150)});document.addEventListener("toggle",function(){setTimeout(scrollables,50)},true);
})();
