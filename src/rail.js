/* الشريط الجانبي: يُبرز القسم الذي في نظر القارئ (IntersectionObserver)؛ بلا مكتبات، ويعمل بلا JS كروابط مرساة عادية. */
(function(){
  var links=[].slice.call(document.querySelectorAll(".nav a[href^='#']"));
  if(!links.length||!("IntersectionObserver" in window))return;
  var by={};links.forEach(function(a){by[a.getAttribute("href").slice(1)]=a});
  var heads=Object.keys(by).map(function(id){return document.getElementById(id)}).filter(Boolean);
  function mark(id){links.forEach(function(a){if(a===by[id])a.setAttribute("aria-current","location");else a.removeAttribute("aria-current")})}
  var io=new IntersectionObserver(function(es){
    es.forEach(function(e){if(e.isIntersecting)mark(e.target.id)});
  },{rootMargin:"0px 0px -70% 0px"});
  heads.forEach(function(h){io.observe(h)});
  if(heads[0])mark(heads[0].id);
})();
