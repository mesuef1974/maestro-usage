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
  window.addEventListener("hashchange",function(){show(location.hash)});
  show(location.hash);
})();
